"""Validation and comparison handling."""
import sys
from ._compatibility.collections.abc import Iterable
from ._compatibility.collections.abc import Iterator
from ._compatibility.collections.abc import Mapping
from ._compatibility.collections.abc import Sequence
from ._compatibility.collections.abc import Set
from ._required import required_predicate
from ._required import required_set
from ._required import required_sequence
from ._utils import nonstringiter
from ._utils import exhaustible
from ._utils import _safesort_key
from ._query.query import (
    BaseElement,
    DictItems,
    _is_collection_of_items,
    Query,
    Result,
)
from .difference import (
    BaseDifference,
    _make_difference,
    NOTFOUND,
)


__all__ = [
    'validate2',
    'valid',
    'ValidationError',
]


def _normalize_data(data):
    if isinstance(data, Query):
        return data.execute()  # <- EXIT! (Returns Result for lazy evaluation.)

    pandas = sys.modules.get('pandas', None)
    if pandas:
        is_series = isinstance(data, pandas.Series)
        is_dataframe = isinstance(data, pandas.DataFrame)

        if (is_series or is_dataframe) and not data.index.is_unique:
            cls_name = data.__class__.__name__
            raise ValueError(('{0} index contains duplicates, must '
                              'be unique').format(cls_name))

        if is_series:
            return DictItems(data.iteritems())  # <- EXIT!

        if is_dataframe:
            gen = ((x[0], x[1:]) for x in data.itertuples())
            if len(data.columns) == 1:
                gen = ((k, v[0]) for k, v in gen)  # Unwrap if 1-tuple.
            return DictItems(gen)  # <- EXIT!

    numpy = sys.modules.get('numpy', None)
    if numpy and isinstance(data, numpy.ndarray):
        # Two-dimentional array, recarray, or structured array.
        if data.ndim == 2 or (data.ndim == 1 and len(data.dtype) > 1):
            data = (tuple(x) for x in data)
            return Result(data, evaluation_type=list)  # <- EXIT!

        # One-dimentional array, recarray, or structured array.
        if data.ndim == 1:
            if len(data.dtype) == 1:         # Unpack single-valued recarray
                data = (x[0] for x in data)  # or structured array.
            else:
                data = iter(data)
            return Result(data, evaluation_type=list)  # <- EXIT!

    return data


def _normalize_requirement(requirement):
    requirement = _normalize_data(requirement)

    if isinstance(requirement, Result):
        return requirement.fetch()  # <- Eagerly evaluate.

    if isinstance(requirement, DictItems):
        return dict(requirement)

    if isinstance(requirement, Iterable) and exhaustible(requirement):
        cls_name = requirement.__class__.__name__
        raise TypeError(("exhaustible type '{0}' cannot be used "
                         "as a requirement").format(cls_name))

    return requirement


class ValidationError(AssertionError):
    """This exception is raised when data validation fails."""

    __module__ = 'datatest'

    def __init__(self, differences, description=None):
        if isinstance(differences, BaseDifference):
            differences = [differences]
        elif not nonstringiter(differences):
            msg = 'expected an iterable of differences, got {0!r}'
            raise TypeError(msg.format(differences.__class__.__name__))

        # Normalize *differences* argument.
        if _is_collection_of_items(differences):
            differences = dict(differences)
        elif exhaustible(differences):
            differences = list(differences)

        if not differences:
            raise ValueError('differences container must not be empty')

        # Initialize properties.
        self._differences = differences
        self._description = description
        self._should_truncate = None
        self._truncation_notice = None

    @property
    def differences(self):
        """A collection of "difference" objects to describe elements
        in the data under test that do not satisfy the requirement.
        """
        return self._differences

    @property
    def description(self):
        """An optional description of the failed requirement."""
        return self._description

    @property
    def args(self):
        """The tuple of arguments given to the exception constructor."""
        return (self._differences, self._description)

    def __str__(self):
        # Prepare a format-differences callable.
        if isinstance(self._differences, dict):
            begin, end = '{', '}'
            all_keys = sorted(self._differences.keys(), key=_safesort_key)
            def sorted_value(key):
                value = self._differences[key]
                if nonstringiter(value):
                    sort_args = lambda diff: _safesort_key(diff.args)
                    return sorted(value, key=sort_args)
                return value
            iterator = iter((key, sorted_value(key)) for key in all_keys)
            format_diff = lambda x: '    {0!r}: {1!r},'.format(x[0], x[1])
        else:
            begin, end = '[', ']'
            sort_args = lambda diff: _safesort_key(diff.args)
            iterator = iter(sorted(self._differences, key=sort_args))
            format_diff = lambda x: '    {0!r},'.format(x)

        # Format differences as a list of strings and get line count.
        if self._should_truncate:
            line_count = 0
            char_count = 0
            list_of_strings = []
            for x in iterator:                  # For-loop used to build list
                line_count += 1                 # iteratively to optimize for
                diff_string = format_diff(x)    # memory (in case the iter of
                char_count += len(diff_string)  # diffs is extremely long).
                if self._should_truncate(line_count, char_count):
                    line_count += sum(1 for x in iterator)
                    end = '    ...'
                    if self._truncation_notice:
                        end += '\n\n{0}'.format(self._truncation_notice)
                    break
                list_of_strings.append(diff_string)
        else:
            list_of_strings = [format_diff(x) for x in iterator]
            line_count = len(list_of_strings)

        # Prepare count-of-differences string.
        count_message = '{0} difference{1}'.format(
            line_count,
            '' if line_count == 1 else 's',
        )

        # Prepare description string.
        if self._description:
            description = '{0} ({1})'.format(self._description, count_message)
        else:
            description = count_message

        # Prepare final output.
        output = '{0}: {1}\n{2}\n{3}'.format(
            description,
            begin,
            '\n'.join(list_of_strings),
            end,
        )
        return output

    def __repr__(self):
        cls_name = self.__class__.__name__
        if self.description:
            return '{0}({1!r}, {2!r})'.format(cls_name, self.differences, self.description)
        return '{0}({1!r})'.format(cls_name, self.differences)


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


def _apply_required_to_data(data, requirement):
    """Apply *requirement* object to *data* and return any differences."""
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


def _apply_required_to_mapping(data, requirement):
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
        result = _apply_required_to_data(value, requirement)
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


def _apply_mapping_to_mapping(data, requirement):
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
        result = _apply_required_to_data(actual, expected)
        if result:
            differences[key] = result

    requirement_items = getattr(requirement, 'iteritems', requirement.items)()
    for key, expected in requirement_items:
        if key not in data_keys:
            result = _apply_required_to_data([], expected)  # Try empty container.
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


def validate2(data, requirement, msg=None):
    """Raise a :exc:`ValidationError` if *data* does not satisfy
    *requirement* or pass without error if data is valid.

    This is a rich comparison function. The given *requirement* can
    be a single predicate, a mapping of predicates, or a list of
    predicates (see :ref:`predicate-docs` for details).

    For values that fail to satisfy their predicates, "difference"
    objects are generated and used to create a :exc:`ValidationError`.
    If a predicate function returns a difference, the result is
    counted as a failure and the returned difference is used in
    place of an automatically generated one.

    **Single Predicates:** When *requirement* is a single predicate,
    all of the values in *data* are checked for the same
    criteria---*data* can be a single value (including strings),
    a mapping, or an iterable::

        data = [2, 4, 6, 8]

        def iseven(x):  # <- Predicate function
            return x % 2 == 0

        datatest.validate(data, iseven)

    **Mappings:** When *requirement* is a dictionary or other
    mapping, the values in *data* are checked against predicates
    of the same key (requires that *data* is also a mapping)::

        data = {
            'A': 1,
            'B': 2,
            'C': ...
        }

        requirement = {  # <- Mapping of predicates
            'A': 1,
            'B': 2,
            'C': ...
        }

        datatest.validate(data, requirement)

    **Sequences:** When *requirement* is list (or other non-tuple,
    non-string sequence), the values in *data* are checked for
    matching order (requires that *data* is a sequence)::

        data = ['A', 'B', 'C', ...]

        requirement = ['A', 'B', 'C', ...]  # <- Sequence of predicates

        datatest.validate(data, requirement)

    .. note::
        This function will either raise an exception or pass without
        errors. To get an explicit True/False return value, users
        should use the :func:`valid` function instead.
    """
    # Setup traceback-hiding for pytest integration.
    __tracebackhide__ = lambda excinfo: excinfo.errisinstance(ValidationError)

    data = _normalize_data(data)
    if isinstance(data, Mapping):
        data = getattr(data, 'iteritems', data.items)()
    requirement = _normalize_requirement(requirement)

    if isinstance(requirement, Mapping):
        result = _apply_mapping_to_mapping(data, requirement)
    elif _is_collection_of_items(data):
        result = _apply_required_to_mapping(data, requirement)
    else:
        result = _apply_required_to_data(data, requirement)

    if result:
        differences, description = result
        if isinstance(differences, dict):
            for k, v in differences.items():
                if isinstance(v, Iterator):
                    differences[k] = list(v)
        message = msg or description or 'does not satisfy requirement'
        raise ValidationError(differences, message)


def valid(data, requirement):
    """Return True if *data* satisfies *requirement* else return False.

    See :func:`validate` for supported *data* and *requirement* values
    and detailed validation behavior.
    """
    try:
        validate2(data, requirement)
    except ValidationError:
        return False
    return True
