# -*- coding: utf-8 -*-
import difflib
from ._compatibility.builtins import *
from ._compatibility import abc
from ._compatibility.collections.abc import Hashable
from ._compatibility.collections.abc import Iterable
from ._compatibility.collections.abc import Mapping
from ._compatibility.collections.abc import Sequence
from ._compatibility.collections.abc import Set
from ._compatibility.functools import wraps
from .difference import BaseDifference
from .difference import Extra
from .difference import Missing
from .difference import _make_difference
from .difference import NOTFOUND
from ._predicate import Predicate
from ._utils import iterpeek
from ._utils import nonstringiter


class FailureInfo(object):
    """An iterator of difference objects and an associated failure
    message. The given *differences* must be an iterable of difference
    objects or a single difference. If provided, *message* should be a
    string that provides some context for the differences.
    """
    def __init__(self, differences, message=None):
        """Initialize instance."""
        if not nonstringiter(differences):
            if isinstance(differences, BaseDifference):
                differences = [differences]
            else:
                cls_name = differences.__class__.__name__
                message = ('differences should be a non-string iterable, '
                           'got {0}: {1!r}')
                raise TypeError(message.format(cls_name, differences))

        first_item, differences = iterpeek(differences, NOTFOUND)
        self._empty = first_item is NOTFOUND
        self._differences = iter(differences)
        self.message = message or 'does not satisfy requirement'

    @property
    def empty(self):
        """True if iterator contains no items or has been exhausted."""
        return self._empty

    def __next__(self):
        try:
            value = next(self._differences)
        except StopIteration:
            self._empty = True
            raise

        if not isinstance(value, BaseDifference):
            cls_name = value.__class__.__name__
            message = 'must contain difference objects, got {0}: {1!r}'
            raise TypeError(message.format(cls_name, value))

        return value

    def next(self):  # <- For Python 2 support.
        return self.__next__()

    def __iter__(self):
        return self


def group_requirement(func):
    """Decorator for group requirement functions."""
    @wraps(func)
    def wrapper(iterable, *args, **kwds):
        result = func(iterable, *args, **kwds)

        if (isinstance(result, Sequence)
                and len(result) == 2
                and not isinstance(result[1], BaseDifference)):
            differences, description = result
        else:
            differences = result
            description = 'does not satisfy requirement'

        if not isinstance(differences, Iterable):
            func_name = getattr(func, '__name__', func.__class__.__name__)
            bad_type = differences.__class__.__name__
            message = ('group requirement {0!r} should return a single '
                       'iterable or a tuple containing an iterable and '
                       'a string description, got {1!r}: {2!r}')
            raise TypeError(message.format(func_name, bad_type, differences))

        first_item, differences = iterpeek(differences, NOTFOUND)
        if first_item is NOTFOUND:
            return None
        return differences, description

    wrapper._group_requirement = True
    return wrapper




class Required(abc.ABC):
    """Base class for Required objects."""
    def failure_message(self):
        """Returns a string to describe the failure."""
        return 'does not satisfy requirement'

    @abc.abstractmethod
    def filterfalse(self, iterable):
        """Return a non-string iterable of differences for values in
        *iterable* that do not satisfy the requirement.
        """
        raise NotImplementedError

    def __call__(self, iterable):
        differences = self.filterfalse(iterable)
        failure_info = FailureInfo(differences, 'does not satisfy requirement')
        if failure_info.empty:
            return None
        return failure_info


class RequiredPredicate(Required):
    def __init__(self, predicate):
        if not isinstance(predicate, Predicate):
            predicate = Predicate(predicate)
        self.predicate = predicate

    def failure_message(self):
        return 'does not satisfy: {0}'.format(self.predicate)

    def filterfalse(self, iterable, show_expected):
        predicate = self.predicate  # Assign directly in local scope
        obj = predicate.obj         # to avoid dot-lookups.

        for element in iterable:
            result = predicate(element)
            if not result:
                yield _make_difference(element, obj, show_expected)

            elif isinstance(result, BaseDifference):
                yield result

    def __call__(self, iterable, show_expected=False):
        # Get differences using *show_expected* argument.
        differences = self.filterfalse(iterable, show_expected)
        failure_info = FailureInfo(differences, 'does not satisfy requirement')
        if failure_info.empty:
            return None
        return failure_info


class RequiredSet(Required):
    def __init__(self, requirement):
        self.requirement = requirement

    def failure_message(self):
        return 'does not satisfy set membership'

    def filterfalse(self, iterable):
        requirement = self.requirement  # Assign locally to avoid dot-lookups.

        matching_elements = set()
        extra_elements = set()
        for element in iterable:
            if element in requirement:
                matching_elements.add(element)
            else:
                extra_elements.add(element)  # <- Build set of Extras so we
                                             #    do not return duplicates.
        for element in requirement:
            if element not in matching_elements:
                yield Missing(element)

        for element in extra_elements:
            yield Extra(element)


def _deephash(obj):
    """Return a "deep hash" value for the given object. If the
    object can not be deep-hashed, a TypeError is raised.
    """
    # Adapted from "deephash" Copyright 2017 Shawn Brown, Apache License 2.0.
    already_seen = {}

    def _hashable_proxy(obj):
        if isinstance(obj, Hashable) and not isinstance(obj, tuple):
            return obj  # <- EXIT!

        # Guard against recursive references in compound objects.
        obj_id = id(obj)
        if obj_id in already_seen:
            return already_seen[obj_id]  # <- EXIT!
        else:
            already_seen[obj_id] = object()  # Token for duplicates.

        # Recurse into compound object to make hashable proxies.
        if isinstance(obj, Sequence):
            proxy = tuple(_hashable_proxy(x) for x in obj)
        elif isinstance(obj, Set):
            proxy = frozenset(_hashable_proxy(x) for x in obj)
        elif isinstance(obj, Mapping):
            items = getattr(obj, 'iteritems', obj.items)()
            items = ((k, _hashable_proxy(v)) for k, v in items)
            proxy = frozenset(items)
        else:
            message = 'unhashable type: {0!r}'.format(obj.__class__.__name__)
            raise TypeError(message)
        return obj.__class__, proxy

    try:
        return hash(obj)
    except TypeError:
        return hash(_hashable_proxy(obj))


class RequiredSequence(Required):
    """Require a specified sequence of objects. If the candidate
    sequence does not match the required sequence, Missing and Extra
    differences will be returned.

    Each difference will contain a two-tuple whose first item is the
    slice-index where the difference starts (in the candidate) and
    whose second item is the non-matching value itself::

        >>> required = RequiredSequence(['a', 'b', 'c'])
        >>> candidate = ['a', 'b', 'x']
        >>> diffs = required(candidate)
        >>> list(diffs)
        [Missing((2, 'c')), Extra((2, 'x'))]

    In the example above, the differences start at slice-index 2 in
    the candidate sequence:

        required sequence   ->  [ 'a', 'b', 'c', ]

        candidate sequence  ->  [ 'a', 'b', 'x', ]
                                 ^    ^    ^    ^
                                 |    |    |    |
        slice index         ->   0    1    2    3
    """
    def __init__(self, sequence):
        if not isinstance(sequence, Sequence):
            cls_name = sequence.__class__.__name__
            message = 'must be sequence, got {0!r}'.format(cls_name)
            raise TypeError(message)
        self.sequence = sequence

    def failure_message(self):
        return 'does not match required sequence'

    def filterfalse(self, iterable):
        if not isinstance(iterable, Sequence):
            iterable = list(iterable)  # <- Needs to be subscriptable.
        sequence = self.sequence  # <- Assign locally to avoid dot-lookups.

        try:
            matcher = difflib.SequenceMatcher(a=iterable, b=sequence)
        except TypeError:
            # Fall-back to slower "deep hash" only if needed.
            data_proxy = tuple(_deephash(x) for x in iterable)
            required_proxy = tuple(_deephash(x) for x in sequence)
            matcher = difflib.SequenceMatcher(a=data_proxy, b=required_proxy)

        for tag, istart, istop, jstart, jstop in matcher.get_opcodes():
            if tag == 'insert':
                jvalues = sequence[jstart:jstop]
                for value in jvalues:
                    yield Missing((istart, value))
            elif tag == 'delete':
                ivalues = iterable[istart:istop]
                for index, value in enumerate(ivalues, start=istart):
                    yield Extra((index, value))
            elif tag == 'replace':
                ivalues = iterable[istart:istop]
                jvalues = sequence[jstart:jstop]

                ijvalues = zip(ivalues, jvalues)
                for index, (ival, jval) in enumerate(ijvalues, start=istart):
                    yield Missing((index, jval))
                    yield Extra((index, ival))

                ilength = istop - istart
                jlength = jstop - jstart
                if ilength < jlength:
                    for value in jvalues[ilength:]:
                        yield Missing((istop, value))
                elif ilength > jlength:
                    remainder = ivalues[jlength:]
                    new_start = istart + jlength
                    for index, value in enumerate(remainder, start=new_start):
                        yield Extra((index, value))
