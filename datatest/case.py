# -*- coding: utf-8 -*-
from __future__ import division
import inspect
from unittest import TestCase

from ._compatibility.builtins import *
from ._compatibility import contextlib

from ._query.query import Query
from ._query.query import Result

from .validation import validate
from .validation import ValidationError

__datatest = True  # Used to detect in-module stack frames (which are
                   # omitted from output).

from .allowance import allowed_missing
from .allowance import allowed_extra
from .allowance import allowed_invalid
from .allowance import allowed_deviation
from .allowance import allowed_percent
from .allowance import allowed_specific
from .allowance import allowed_keys
from .allowance import allowed_args
from .allowance import allowed_fuzzy
from .allowance import allowed_limit


def _pytest_tracebackhide(excinfo):
    """Pytest integration for hiding error tracebacks. To use, assign
    to the special traceback-hide value inside a function or method::

        __tracebackhide__ = _pytest_tracebackhide
    """
    return excinfo.errisinstance(ValidationError)


class DataTestCase(TestCase):
    """This class extends :py:class:`unittest.TestCase` with methods
    for asserting data validity. In addition to the new functionality,
    familiar methods (like setUp, addCleanup, etc.) are still
    available.
    """
    maxDiff = getattr(TestCase, 'maxDiff', 80 * 8)  # Uses default in 3.1 and 2.6.

    def _apply_validation(self, function, *args, **kwds):
        """Wrapper to call *function* (with given *args and **kwds)
        and manage truncation behavior if a ValidationError is raised.

        The *function* must be a callable object and it should pass
        silently or raise a ValidationError.
        """
        try:
            function(*args, **kwds)
        except ValidationError as err:
            def should_truncate(line_count, char_count):
                return self.maxDiff and (char_count > self.maxDiff)
            err._should_truncate = should_truncate

            err._truncation_notice = \
                'Diff is too long. Set self.maxDiff to None to see it.'

            raise err

    def assertValid(self, data, requirement, msg=None):
        """Fail if the *data* under test does not satisfy the
        *requirement*.

        The given *data* can be a set, sequence, iterable, mapping,
        or other object. The *requirement* type determines how the
        data is validated (see below).

        **Set membership:** When *requirement* is a set, elements
        in *data* are checked for membership in this set. On failure,
        a :class:`ValidationError` is raised which contains
        :class:`Missing` or :class:`Extra` differences::

            def test_mydata(self):
                data = ...
                requirement = {'A', 'B', 'C', ...}  # <- set
                self.assertValid(data, requirement)

        **Regular expression match:** When *requirement* is a regular
        expression object, elements in *data* are checked to see if
        they match the given pattern. On failure, a
        :class:`ValidationError` is raised with :class:`Invalid`
        differences::

            def test_mydata(self):
                data = ...
                requirement = re.compile(r'^[0-9A-F]*$')  # <- regex
                self.assertValid(data, requirement)

        **Sequence order:** When *requirement* is a list or other
        sequence, elements in *data* are checked for matching order
        and value. On failure, an :py:class:`AssertionError` is
        raised::

            def test_mydata(self):
                data = ...
                requirement = ['A', 'B', 'C', ...]  # <- sequence
                self.assertValid(data, requirement)

        **Mapping comparison:** When *requirement* is a dict (or other
        mapping), elements of matching keys are checked for equality.
        This comparison also requires *data* to be a mapping. On
        failure, a :class:`ValidationError` is raised with
        :class:`Invalid` or :class:`Deviation` differences::

            def test_mydata(self):
                data = ...  # <- Should also be a mapping.
                requirement = {'A': 1, 'B': 2, 'C': ...}  # <- mapping
                self.assertValid(data, requirement)

        **Function comparison:** When *requirement* is a function or
        other callable, elements in *data* are checked to see if they
        evaluate to True. When the function returns False, a
        :class:`ValidationError` is raised with :class:`Invalid`
        differences::

            def test_mydata(self):
                data = ...
                def requirement(x):  # <- callable (helper function)
                    return x.isupper()
                self.assertValid(data, requirement)

        **Other comparison:** When *requirement* does not match any
        previously specified type (e.g., str, float, etc.), elements
        in *data* are checked to see if they are equal to the given
        object. On failure, a :class:`ValidationError` is raised which
        contains :class:`Invalid` or :class:`Deviation` differences::

            def test_mydata(self):
                data = ...
                requirement = 'FOO'
                self.assertValid(data, requirement)
        """
        __tracebackhide__ = _pytest_tracebackhide
        self._apply_validation(validate, data, requirement, msg=msg)

    def assertValidApprox(self, data, requirement, places=None, msg=None, delta=None):
        """Wrapper for :meth:`validate.approx`."""
        __tracebackhide__ = _pytest_tracebackhide
        self._apply_validation(validate.approx, data, requirement,
                               places=places, msg=msg, delta=delta)

    def assertValidFuzzy(self, data, requirement, cutoff=0.6, msg=None):
        """Wrapper for :meth:`validate.fuzzy`."""
        __tracebackhide__ = _pytest_tracebackhide
        self._apply_validation(validate.fuzzy, data, requirement,
                               cutoff=cutoff, msg=msg)

    def assertValidOrder(self, data, sequence, msg=None):
        """Wrapper for :meth:`validate.order`."""
        __tracebackhide__ = _pytest_tracebackhide
        self._apply_validation(validate.order, data, sequence, msg=msg)

    def assertValidOutliers(self, data, requirement=None,
                            multiplier=2.2, msg=None, rounding=True):
        """Wrapper for :meth:`validate.outliers`."""
        __tracebackhide__ = _pytest_tracebackhide
        self._apply_validation(validate.outliers,
                               data,
                               requirement=requirement,
                               multiplier=multiplier,
                               msg=msg,
                               rounding=rounding)

    def assertValidPredicate(self, data, requirement, msg=None):
        """Wrapper for :meth:`validate.predicate`."""
        __tracebackhide__ = _pytest_tracebackhide
        self._apply_validation(validate.predicate, data, requirement, msg=msg)

    def assertValidSet(self, data, requirement, msg=None):
        """Wrapper for :meth:`validate.set`."""
        __tracebackhide__ = _pytest_tracebackhide
        self._apply_validation(validate.set, data, requirement, msg=msg)

    def assertValidSubset(self, data, requirement, msg=None):
        """Wrapper for :meth:`validate.subset`."""
        __tracebackhide__ = _pytest_tracebackhide
        self._apply_validation(validate.subset, data, requirement, msg=msg)

    def assertValidSuperset(self, data, requirement, msg=None):
        """Wrapper for :meth:`validate.superset`."""
        __tracebackhide__ = _pytest_tracebackhide
        self._apply_validation(validate.superset, data, requirement, msg=msg)

    def assertValidUnique(self, data, msg=None):
        """Wrapper for :meth:`validate.unique`."""
        __tracebackhide__ = _pytest_tracebackhide
        self._apply_validation(validate.unique, data, msg=msg)

    def allowedMissing(self, msg=None):
        """Allows :class:`Missing` elements without triggering a test
        failure::

            with self.allowedMissing():
                data = {'A', 'B'}  # <- 'C' is missing
                requirement = {'A', 'B', 'C'}
                self.assertValid(data, requirement)
        """
        return allowed_missing(msg)

    def allowedExtra(self, msg=None):
        """Allows :class:`Extra` elements without triggering a test
        failure::

            with self.allowedExtra():
                data = {'A', 'B', 'C', 'D'}  # <- 'D' is extra
                requirement = {'A', 'B', 'C'}
                self.assertValid(data, requirement)
        """
        return allowed_extra(msg)

    def allowedInvalid(self, msg=None):
        """Allows :class:`Invalid` elements without triggering a test
        failure::

            with self.allowedInvalid():
                data = {'xxx': 'A', 'yyy': 'E'}  # <- 'E' is invalid
                requirement = {'xxx': 'A', 'yyy': 'B'}
                self.assertValid(data, requirement)
        """
        return allowed_invalid(msg)

    def allowedDeviation(self, lower, upper=None, msg=None):
        """
        allowedDeviation(tolerance, /, msg=None)
        allowedDeviation(lower, upper, msg=None)

        See documentation for full details.
        """
        return allowed_deviation(lower, upper, msg)

    def allowedPercent(self, lower, upper=None, msg=None):
        """
        allowedPercent(tolerance, /, msg=None)
        allowedPercent(lower, upper, msg=None)

        See documentation for full details.
        """
        return allowed_percent(lower, upper, msg)

    def allowedPercentDeviation(self, lower, upper=None, msg=None):
        """alias of :meth:`DataTestCase.allowedPercent`"""
        return self.allowedPercent(lower, upper, msg)

    def allowedSpecific(self, differences, msg=None):
        """Allows individually specified *differences* without
        triggering a test failure::

            two_diffs = self.allowedSpecific([
                Missing('C'),
                Extra('D'),
            ])
            with two_diffs:
                data = {'A', 'B', 'D'}  # <- 'D' extra, 'C' missing
                requirement = {'A', 'B', 'C'}
                self.assertValid(data, requirement)

        The *differences* argument can be a :py:obj:`list` or
        :py:obj:`dict` of differences or a single difference.
        """
        return allowed_specific(differences, msg)

    def allowedKeys(self, predicate, msg=None):
        """Allows differences in a mapping whose keys satisfy the
        given *predicate*.
        """
        return allowed_keys(predicate, msg)

    def allowedArgs(self, predicate, msg=None):
        """Allows differences in a mapping whose args satisfy the
        given *predicate*.
        """
        return allowed_args(predicate, msg)

    def allowedFuzzy(self, cutoff=0.6, msg=None):
        """Allows invalid strings that match their expected value with
        a similarity greater than or equal to *cutoff* (default 0.6).

        Similarity measures are determined using the ratio() method of
        the difflib.SequenceMatcher class. The values range from 1.0
        (exactly the same) to 0.0 (completely different).
        """
        return allowed_fuzzy(cutoff=cutoff, msg=msg)

    def allowedLimit(self, number, msg=None):
        """Allows a limited *number* of differences without triggering
        a test failure::

            with self.allowedLimit(2):  # Allows up to two differences.
                data = ['47306', '1370', 'TX']  # <- '1370' and 'TX' invalid
                requirement = re.compile('^\d{5}$')
                self.assertValid(data, requirement)

        If the count of differences exceeds the given *number*, the
        test will fail with a :class:`ValidationError` containing all
        observed differences.
        """
        return allowed_limit(number, msg)


# Prettify default signature of methods that accept multiple signatures.
# This only works for Python 3.3 and newer--older versions will simply
# have the original method sigture.
with contextlib.suppress(AttributeError):  # inspect.Signature() is new in 3.3
    DataTestCase.allowedDeviation.__signature__ = inspect.Signature([
        inspect.Parameter('self', inspect.Parameter.POSITIONAL_ONLY),
        inspect.Parameter('tolerance', inspect.Parameter.POSITIONAL_ONLY),
        inspect.Parameter('msg', inspect.Parameter.POSITIONAL_OR_KEYWORD),
    ])

    DataTestCase.allowedPercentDeviation.__signature__ = inspect.Signature([
        inspect.Parameter('self', inspect.Parameter.POSITIONAL_ONLY),
        inspect.Parameter('tolerance', inspect.Parameter.POSITIONAL_ONLY),
        inspect.Parameter('msg', inspect.Parameter.POSITIONAL_OR_KEYWORD),
    ])
