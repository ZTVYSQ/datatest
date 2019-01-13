# -*- coding: utf-8 -*-
import difflib
from types import FunctionType
from ._compatibility.builtins import *
from ._compatibility import abc
from ._compatibility.collections.abc import Hashable
from ._compatibility.collections.abc import Iterable
from ._compatibility.collections.abc import Mapping
from ._compatibility.collections.abc import Sequence
from ._compatibility.collections.abc import Set
from ._compatibility.functools import wraps
from ._compatibility.itertools import chain
from .difference import BaseDifference
from .difference import Extra
from .difference import Missing
from .difference import _make_difference
from .difference import NOTFOUND
from ._predicate import Predicate
from ._query.query import BaseElement
from ._query.query import _is_collection_of_items
from ._utils import iterpeek
from ._utils import nonstringiter


def _build_description(obj):
    """Build failure description for required_predicate() or
    for a group-requirement function that does not return its
    own description.
    """
    if isinstance(obj, FunctionType):
        docstring = getattr(obj, '__doc__', None)
        if docstring:
            first_line = docstring.lstrip().partition('\n')[0]
            description = first_line.rstrip()
            if description:
                return description  # <- EXIT!

    name = getattr(obj, '__name__', None)
    if name:
        if name.startswith('<'):  # E.g., "<lambda>".
            obj_repr = name
        else:
            if callable(obj) and not isinstance(obj, type):
                obj_repr = "{0}()".format(name)
            else:
                obj_repr = "'{0}'".format(name)
    else:
        obj_repr = repr(obj)

    return 'does not satisfy {0}'.format(obj_repr)


def _wrap_differences(differences, func):
    """A generator function to wrap and iterable of differences
    and verify that each item returned is a difference object.
    If any non-difference objects are encountered, a TypeError
    is raised.

    The given *differences* should be an iterable of difference
    objects and *func* should be the group requirement function
    used to generate the differences.
    """
    for value in differences:
        if not isinstance(value, BaseDifference):
            func_name = getattr(func, '__name__', func.__class__.__name__)
            cls_name = value.__class__.__name__
            message = ('iterable from group requirement {0!r} must '
                       'contain difference objects, got {1!r}: {2!r}')
            raise TypeError(message.format(func_name, cls_name, value))
        yield value


def _normalize_requirement_result(result, func):
    """Takes the *result* of a requirement function as well as the
    *func* itself and returns a normalized differences-description
    2-tuple or None.
    """
    if (isinstance(result, Sequence)
            and len(result) == 2
            and not isinstance(result[1], BaseDifference)):
        differences, description = result
    else:
        differences = result
        description = _build_description(func)

    if not isinstance(differences, Iterable):
        func_name = getattr(func, '__name__', func.__class__.__name__)
        bad_type = differences.__class__.__name__
        message = ('requirement function {0!r} should return a single '
                   'iterable or a tuple containing an iterable and a '
                   'string description, got {1!r}: {2!r}')
        raise TypeError(message.format(func_name, bad_type, differences))

    first_item, differences = iterpeek(differences, NOTFOUND)
    if first_item is NOTFOUND:
        return None
    differences = _wrap_differences(differences, func)
    return differences, description


def group_requirement(func):
    """A decorator for group requirement functions. A group requirement
    function should accept an iterable and return values appropriate
    for instantiating a :exc:`ValidationError` (either an iterable of
    differences or a 2-tuple containing an iterable of differences and
    a description).
    """
    if getattr(func, '_group_requirement', False):
        return func  # <- EXIT!

    @wraps(func)
    def wrapper(iterable, *args, **kwds):
        result = func(iterable, *args, **kwds)
        return _normalize_requirement_result(result, func)

    wrapper._group_requirement = True
    return wrapper


def required_predicate(requirement, show_expected=False):
    """Accepts a *requirement* object and returns a group requirement
    that tests for a predicate.
    """
    @group_requirement
    def _required_predicate(iterable):  # Closes over *requirement*
                                        # and *show_expected*.
        def generate_differences(requirement, iterable):
            predicate = Predicate(requirement)
            for element in iterable:
                result = predicate(element)
                if not result:
                    yield _make_difference(element, requirement, show_expected)
                elif isinstance(result, BaseDifference):
                    yield result

        differences = generate_differences(requirement, iterable)
        description = _build_description(requirement)
        return differences, description

    return _required_predicate


def required_set(requirement):
    """Returns a group requirement function that checks for set membership."""
    @group_requirement
    def _required_set(iterable):  # Closes over *requirement*.
        matches = set()
        extras = set()
        for element in iterable:
            if element in requirement:
                matches.add(element)
            else:
                extras.add(element)  # <- Build set of Extras so we
                                     #    do not return duplicates.
        missing = (x for x in requirement if x not in matches)

        differences = chain(
            (Missing(x) for x in missing),
            (Extra(x) for x in extras),
        )
        return differences, 'does not satisfy set membership'

    return _required_set


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


def required_sequence(requirement):
    """Returns a group requirement function that checks for sequence
    order. If the candidate sequence does not match the required
    sequence, Missing and Extra differences will be returned.

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

    .. note::
        This function uses difflib.SequenceMatcher() which
        expects hashable values. If given unhashable values,
        required_sequence() will make a best effort attempt
        to build a "deep hash" to sort many types of otherwise
        unhashable objects.
    """
    if not isinstance(requirement, Sequence):
        cls_name = requirement.__class__.__name__
        message = 'must be sequence, got {0!r}'.format(cls_name)
        raise TypeError(message)

    @group_requirement
    def _required_sequence(iterable):  # Closes over *requirement*.

        def generate_differences(iterable, sequence):
            if not isinstance(iterable, Sequence):
                iterable = list(iterable)  # <- Needs to be subscriptable.

            try:
                matcher = difflib.SequenceMatcher(a=iterable, b=requirement)
            except TypeError:
                # Fall-back to slower "deep hash" only if needed.
                data_proxy = tuple(_deephash(x) for x in iterable)
                required_proxy = tuple(_deephash(x) for x in requirement)
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

        differences = generate_differences(iterable, requirement)
        return differences, 'does not match required sequence'

    return _required_sequence


def _get_group_requirement(requirement, show_expected=False):
    """Make sure *requirement* is a group requirement."""
    if getattr(requirement, '_group_requirement', False):
        return requirement

    if isinstance(requirement, Set):
        return required_set(requirement)

    if (not isinstance(requirement, BaseElement)
            and isinstance(requirement, Sequence)):
        return required_sequence(requirement)

    return required_predicate(requirement, show_expected)


def _data_vs_requirement(data, requirement):
    """Validate *data* using *requirement* and return any differences."""
    # Handle *data* that is a container of multiple elements.
    if not isinstance(data, BaseElement):
        requirement = _get_group_requirement(requirement)
        return requirement(data)  # <- EXIT!

    # Handle *data* that is a single-value BaseElement.
    requirement = _get_group_requirement(requirement, show_expected=True)
    result = requirement([data])
    if result:
        differences, description = result
        differences = list(differences)
        if len(differences) == 1:
            differences = differences[0]  # Unwrap if single difference.
        return differences, description
    return None


def _datadict_vs_requirement(data, requirement):
    """Apply *requirement* object to mapping of *data* values and
    return a mapping of any differences and a description.
    """
    if isinstance(data, Mapping):
        data_items = getattr(data, 'iteritems', data.items)()
    elif _is_collection_of_items(data):
        data_items = data
    else:
        raise TypeError('data must be mapping or iterable of key-value items')

    requirement = _get_group_requirement(requirement)

    differences = dict()
    for key, value in data_items:
        result = _data_vs_requirement(value, requirement)
        if result:
            differences[key] = result

    if not differences:
        return None  # <- EXIT!

    # Get first description from results.
    itervalues = getattr(differences, 'itervalues', differences.values)()
    description = next((x for _, x in itervalues), None)

    # Format dictionary values and finalize description.
    for key, value in getattr(differences, 'iteritems', differences.items)():
        diffs, desc = value
        differences[key] = diffs
        if description and description != desc:
            description = None

    return differences, description


def _datadict_vs_requirementdict(data, requirement):
    """Apply mapping of *requirement* values to a mapping of *data*
    values and return a mapping of any differences and a description
    or None.
    """
    if isinstance(data, Mapping):
        data_items = getattr(data, 'iteritems', data.items)()
    elif _is_collection_of_items(data):
        data_items = data
    else:
        raise TypeError('data must be mapping or iterable of key-value items')

    data_keys = set()
    differences = dict()

    for key, actual in data_items:
        data_keys.add(key)
        expected = requirement.get(key, NOTFOUND)
        result = _data_vs_requirement(actual, expected)
        if result:
            differences[key] = result

    requirement_items = getattr(requirement, 'iteritems', requirement.items)()
    for key, expected in requirement_items:
        if key not in data_keys:
            result = _data_vs_requirement([], expected)  # Try empty container.
            if not result:
                diff = _make_difference(NOTFOUND, expected)
                result = (diff, NOTFOUND)
            differences[key] = result

    if not differences:
        return None  # <- EXIT!

    # Get first description from results.
    itervalues = getattr(differences, 'itervalues', differences.values)()
    filtered = (x for _, x in itervalues if x is not NOTFOUND)
    description = next(filtered, None)

    # Format dictionary values and finalize description.
    for key, value in getattr(differences, 'iteritems', differences.items)():
        diffs, desc = value
        differences[key] = diffs
        if description and description != desc and desc is not NOTFOUND:
            description = None

    return differences, description


def whole_requirement(func):
    """A decorator for whole requirement functions. A whole requirement
    function should accept a *data* object and return values appropriate
    for instantiating a :exc:`ValidationError` (either an iterable of
    differences or a 2-tuple containing an iterable of differences and
    a description).
    """
    if getattr(func, '_whole_requirement', False):
        return func  # <- EXIT!

    func._whole_requirement = True
    return func

    @wraps(func)
    def wrapper(data):
        result = func(data)
        return _normalize_requirement_result(result, func)

    wrapper._whole_requirement = True
    return wrapper


def requirement_handler(requirement):
    """Returns a while requirement function that provides default
    validation behavior.
    """
    @whole_requirement
    def _requirement_handler(data):
        """Default requirement handler."""
        if isinstance(requirement, Mapping):
            result = _datadict_vs_requirementdict(data, requirement)
        elif isinstance(data, Mapping) or _is_collection_of_items(data):
            result = _datadict_vs_requirement(data, requirement)
        else:
            result = _data_vs_requirement(data, requirement)
        return result

    return _requirement_handler


def _get_required_func(requirement):
    """Returns a whole-object requirement handler."""
    if getattr(requirement, '_whole_requirement', False):
        return requirement
    return requirement_handler(requirement)


class BaseRequirement(abc.ABC):
    @abc.abstractmethod
    def check_data(self, data):
        raise NotImplementedError()

    def _verify_difference(self, obj):
        """Raise an error if *obj* is not a subclass of BaseDifference."""
        if not isinstance(obj, BaseDifference):
            slf_name = self.__class__.__name__
            obj_name = obj.__class__.__name__
            message = ('values returned from {0} must be '
                       'difference objects, got {1}: {2!r}')
            raise TypeError(message.format(slf_name, obj_name, obj))

    def _wrap_difference_group(self, group):
        """A generator function to wrap an iterable of differences and
        verify that each value is a difference object.
        """
        for value in group:
            self._verify_difference(value)
            yield value

    def _wrap_difference_items(self, items):
        """A generator function to wrap an iterable of key/value pairs
        and verify that each value is a difference or an iterable of
        difference objects.
        """
        for key, value in items:
            if nonstringiter(value):
                value = self._wrap_difference_group(value)
            else:
                self._verify_difference(value)
            yield key, value

    def _normalize(self, result):
        """Return a normalized *result* as a 2-tuple (containing an
        iterable of differences and a string description) or None.
        """
        if (isinstance(result, Sequence)
                and len(result) == 2
                and not isinstance(result[1], BaseDifference)):
            differences, description = result
        else:
            differences = result
            description = ''

        if not description:
            description = 'does not satisfy {0}'.format(self.__class__.__name__)

        if not isinstance(differences, Iterable):
            slf_name = self.__class__.__name__
            dff_name = differences.__class__.__name__
            message = (
                '{0!r} should return an iterable or a tuple containing '
                'an iterable and a string description, got {1!r}: {2!r}'
            )
            raise TypeError(message.format(slf_name, dff_name, differences))

        first_item, differences = iterpeek(differences, NOTFOUND)

        if first_item is NOTFOUND:
            return None  # <- EXIT!

        if isinstance(first_item, tuple):
            differences = self._wrap_difference_items(differences)
        else:
            differences = self._wrap_difference_group(differences)
        return differences, description

    def __call__(self, data):
        result = self.check_data(data)
        return self._normalize(result)


class ItemsRequirement(BaseRequirement):
    @abc.abstractmethod
    def check_items(self, items):
        raise NotImplementedError()

    def check_data(self, data):
        if isinstance(data, Mapping):
            data = getattr(data, 'iteritems', data.items)()
        return self.check_items(data)


_INCONSISTENT = object()  # Marker for inconsistent descriptions.

class GroupRequirement(BaseRequirement):
    @abc.abstractmethod
    def check_group(self, group):
        raise NotImplementedError()

    def check_items(self, items):
        differences = []
        description = ''

        for key, value in items:
            if isinstance(value, BaseElement):
                diff, desc = self.check_group([value])
                diff = list(diff)
                if len(diff) == 1:
                    diff = diff[0]  # Unwrap if single difference.
                if not diff:
                    continue
            else:
                diff, desc = self.check_group(value)
                first_element, diff = iterpeek(diff, None)
                if not first_element:
                    continue

            differences.append((key, diff))

            if description == desc or description is _INCONSISTENT:
                continue

            if not description:
                description = desc
            else:
                description = _INCONSISTENT

        if description is _INCONSISTENT:
            description = ''
        return differences, description

    def check_data(self, data):
        if isinstance(data, Mapping):
            data = getattr(data, 'iteritems', data.items)()

        if _is_collection_of_items(data):
            return self.check_items(data)

        if isinstance(data, BaseElement):
            data = [data]
        return self.check_group(data)


class RequiredPredicate(GroupRequirement):
    """A requirement to test that data matches a predicate object."""
    def __init__(self, obj, show_expected=False):
        self._pred = Predicate(obj)
        self._obj = obj
        self.show_expected = show_expected

    def _get_differences(self, group):
        pred = self._pred
        obj = self._obj
        show_expected = self.show_expected
        for element in group:
            result = pred(element)
            if not result:
                yield _make_difference(element, obj, show_expected)
            elif isinstance(result, BaseDifference):
                yield result

    def check_group(self, group):
        differences = self._get_differences(group)
        description = _build_description(self._obj)
        return differences, description

    def check_items(self, items):
        pred = self._pred
        obj = self._obj
        show_expected = self.show_expected

        differences = []
        for key, value in items:
            if isinstance(value, BaseElement):
                result = pred(value)
                if not result:
                    diff = _make_difference(value, obj, show_expected)
                elif isinstance(result, BaseDifference):
                    diff = result
                else:
                    continue
            else:
                diff, desc = self.check_group(value)
                first_element, diff = iterpeek(diff, None)
                if not first_element:
                    continue
            differences.append((key, diff))

        description = _build_description(self._obj)
        return differences, description


class RequiredSet(GroupRequirement):
    """A requirement to test data for set membership."""
    def __init__(self, requirement):
        self._set = set(requirement)

    def check_group(self, group):
        requirement = self._set

        matches = set()
        extras = set()
        for element in group:
            if element in requirement:
                matches.add(element)
            else:
                extras.add(element)  # <- Build set of Extras so we
                                     #    do not return duplicates.
        missing = (x for x in requirement if x not in matches)

        differences = chain(
            (Missing(x) for x in missing),
            (Extra(x) for x in extras),
        )
        return differences, 'does not satisfy set membership'


class RequiredSequence(GroupRequirement):
    """A requirement to test data for sequence order."""
    def __init__(self, sequence):
        if not isinstance(sequence, Sequence):
            cls_name = sequence.__class__.__name__
            message = 'must be sequence, got {0!r}'.format(cls_name)
            raise TypeError(message)
        self.sequence = sequence

    def _generate_differences(self, group):
        if not isinstance(group, Sequence):
            group = list(group)  # <- Needs to be subscriptable.

        requirement = self.sequence

        try:
            # Try sequences directly.
            matcher = difflib.SequenceMatcher(a=group, b=requirement)
        except TypeError:
            # Fall-back to slower proxy method when needed.
            data_proxy = tuple(_deephash(x) for x in group)
            required_proxy = tuple(_deephash(x) for x in requirement)
            matcher = difflib.SequenceMatcher(a=data_proxy, b=required_proxy)

        for tag, istart, istop, jstart, jstop in matcher.get_opcodes():
            if tag == 'insert':
                jvalues = requirement[jstart:jstop]
                for value in jvalues:
                    yield Missing((istart, value))
            elif tag == 'delete':
                ivalues = group[istart:istop]
                for index, value in enumerate(ivalues, start=istart):
                    yield Extra((index, value))
            elif tag == 'replace':
                ivalues = group[istart:istop]
                jvalues = requirement[jstart:jstop]

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

    def check_group(self, group):
        differences = self._generate_differences(group)
        return differences, 'does not match required sequence'


class RequiredMapping(ItemsRequirement):
    def __init__(self, mapping):
        if not isinstance(mapping, Mapping):
            mapping = dict(mapping)
        self.mapping = mapping

    @staticmethod
    def _get_group_requirement(obj):
        if isinstance(obj, GroupRequirement):
            return obj

        if isinstance(obj, Set):
            return RequiredSet(obj)

        if isinstance(obj, Sequence) and not isinstance(obj, BaseElement):
            return RequiredSequence(obj)

        return RequiredPredicate(obj)

    def _get_differences(self, items):
        required_mapping = self.mapping

        for item in items:
            try:
                key, value = item
            except ValueError:
                msg = ('item {0!r} is not a valid key/value pair; {1} '
                       'expects a mapping or iterable of key/value pairs')
                raise ValueError(msg.format(item, self.__class__.__name__))

            expected = required_mapping.get(key, NOTFOUND)

            if isinstance(value, BaseElement):
                pred = Predicate(expected)
                result = pred(value)
                if not result:
                    yield key, _make_difference(value, expected, show_expected=True)
                elif isinstance(result, BaseDifference):
                    yield key, result
            else:
                requirement = self._get_group_requirement(expected)
                diff, desc = requirement.check_group(value)
                first_item, diff = iterpeek(diff, None)
                if first_item:
                    yield key, diff

    def check_items(self, items):
        differences = self._get_differences(items)
        return differences, 'does not satisfy mapping requirements'
