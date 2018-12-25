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
from ._utils import iterpeek


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
            message = ('group requirement {0!r} should return a single '
                       'iterable or a tuple containing an iterable and '
                       'a string description, got {1!r}: {2!r}')
            raise TypeError(message.format(func_name, bad_type, differences))

        first_item, differences = iterpeek(differences, NOTFOUND)
        if first_item is NOTFOUND:
            return None
        differences = _wrap_differences(differences, func)
        return differences, description

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
