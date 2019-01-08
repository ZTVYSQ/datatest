# -*- coding: utf-8 -*-
from __future__ import absolute_import
from . import _unittest as unittest
from datatest._compatibility.collections.abc import Iterator
from datatest import Missing
from datatest import Extra
from datatest import Deviation
from datatest import Invalid
from datatest._required import _build_description
from datatest._required import _wrap_differences
from datatest._required import group_requirement
from datatest._required import required_predicate
from datatest._required import required_set
from datatest._required import required_sequence
from datatest._required import _get_group_requirement
from datatest._required import _data_vs_requirement
from datatest._required import _datadict_vs_requirement
from datatest._required import _datadict_vs_requirementdict
from datatest._required import _normalize_requirement_result
from datatest._required import BaseRequirement
from datatest._required import RequiredItems
from datatest._required import RequiredGroup


class TestBuildDescription(unittest.TestCase):
    def test_docstring_messy(self):
        def func(x):
            """  \n  line one  \nline two"""  # <- Deliberately messy
            return False                      #    whitespace, do not
                                              #    change.
        description = _build_description(func)
        self.assertEqual(description, 'line one')

    def test_docstring_whitespace(self):
        def func(x):
            """    \n    """  # <- Docstring is entirely whitespace.
            return False

        description = _build_description(func)
        self.assertEqual(description, 'does not satisfy func()')

    def test_docstring_is_None(self):
        def func(x):
            return False
        description = _build_description(func)
        self.assertEqual(description, 'does not satisfy func()')

    def test_builtin_type(self):
        description = _build_description(float)
        msg = 'should be name in single quotes'
        self.assertEqual(description, "does not satisfy 'float'", msg=msg)

    def test_user_defined_type(self):
        """User-defined classes should use the name in quotes (not the
        docstring).
        """
        class MyClass(object):
            """A dummy class for testing."""
            def __call__(self, *args):
                """Always returns False."""
                return False

            def __repr__(self):
                return '**dummy class**'

        self.assertTrue(MyClass.__doc__, msg='make sure class has docstring')

        description = _build_description(MyClass)
        msg = 'user defined classes should work same as built-in types (name in quotes)'
        self.assertEqual(description, "does not satisfy 'MyClass'", msg=msg)

    def test_lambda_expression(self):
        description = _build_description(lambda x: False)
        msg = 'if object is in angle brackets, should not use quotes'
        self.assertEqual(description, "does not satisfy <lambda>", msg=msg)

    def test_no_docstring_no_name(self):
        """Non-type objects with no name and no docstring should use
        the object's repr().
        """
        description = _build_description('abc')
        self.assertEqual(description, "does not satisfy 'abc'")

        description = _build_description(123)
        self.assertEqual(description, "does not satisfy 123")

        class MyClass(object):
            """A dummy class for testing."""
            def __call__(self, *args):
                """Always returns False."""
                return False

            def __repr__(self):
                return '**dummy class**'

        myinstance = MyClass()  # <- Instance of user-defined class.
        description = _build_description(myinstance)
        self.assertEqual(description, "does not satisfy **dummy class**")


class TestWrapDifferences(unittest.TestCase):
    def test_good_values(self):
        diffs = [Missing(1), Missing(2), Missing(3)]
        wrapped = _wrap_differences(diffs, lambda x: [])
        msg = 'yielding difference objects should work without issue'
        self.assertEqual(list(wrapped), diffs, msg=msg)

    def test_bad_value(self):
        diffs = [Missing(1), Missing(2), 123]
        wrapped = _wrap_differences(diffs, lambda x: [])
        msg = 'yielding a non-difference object should fail with a useful message'
        pattern = ("iterable from group requirement '<lambda>' must "
                   "contain difference objects, got 'int': 123")
        with self.assertRaisesRegex(TypeError, pattern, msg=msg):
            list(wrapped)  # <- Fully evaluate generator.


class TestNormalizeRequirementResult(unittest.TestCase):
    def setUp(self):
        def func(iterable):  # <- A dummy function.
            return None
        self.func = func

    def test_iter_and_description(self):
        result = ([Missing(1)], 'error message')  # <- Iterable and description.
        diffs, desc = _normalize_requirement_result(result, self.func)
        self.assertEqual(list(diffs), [Missing(1)])
        self.assertEqual(desc, 'error message')

    def test_iter_alone(self):
        result = [Missing(1)]  # <- Iterable only, no description.
        diffs, desc = _normalize_requirement_result(result, self.func)
        self.assertEqual(list(diffs), [Missing(1)])
        self.assertEqual(desc, 'does not satisfy func()', msg='gets default description')

    def test_tuple_of_diffs(self):
        """Should not mistake a 2-tuple of difference objects for a
        2-tuple containing an iterable of differences with a string
        description.
        """
        result = (Missing(1), Missing(2))  # <- A 2-tuple of diffs.
        diffs, desc = _normalize_requirement_result(result, self.func)
        self.assertEqual(list(diffs), [Missing(1), Missing(2)])
        self.assertEqual(desc, 'does not satisfy func()', msg='gets default description')

    def test_empty_iter(self):
        """Empty iterable result should be converted to None."""
        result = (iter([]), 'error message')  # <- Empty iterable and description.
        normalized = _normalize_requirement_result(result, self.func)
        self.assertIsNone(normalized)

        result = iter([])  # <- Empty iterable
        normalized = _normalize_requirement_result(result, self.func)
        self.assertIsNone(normalized)

    def test_bad_types(self):
        """Bad return types should trigger TypeError."""
        with self.assertRaisesRegex(TypeError, 'should return .* iterable'):
            result = (Missing(1), 'error message')  # <- Non-iterable and description.
            _normalize_requirement_result(result, self.func)

        with self.assertRaisesRegex(TypeError, 'should return .* iterable'):
            result = None  # <- None only.
            _normalize_requirement_result(result, self.func)

        with self.assertRaisesRegex(TypeError, 'should return .* an iterable and a string'):
            result = (None, 'error message')  # <- None and description
            _normalize_requirement_result(result, self.func)


class TestGroupRequirement(unittest.TestCase):
    def test_group_requirement_flag(self):
        def func(iterable):
            return [Missing(1)], 'error message'

        self.assertFalse(hasattr(func, '_group_requirement'))

        func = group_requirement(func)  # <- Apply decorator.
        self.assertTrue(hasattr(func, '_group_requirement'))
        self.assertTrue(func._group_requirement)

    def test_group_requirement_wrapping(self):
        """Decorating a group requirement should return the original
        object, it should not double-wrap existing group requirements.
        """
        @group_requirement
        def func1(iterable):
            return [Missing(1)], 'error message'

        func2 = group_requirement(func1)

        self.assertIs(func1, func2)


class TestRequiredPredicate(unittest.TestCase):
    def setUp(self):
        isdigit = lambda x: x.isdigit()
        self.requirement = required_predicate(isdigit)

    def test_all_true(self):
        data = iter(['10', '20', '30'])
        result = self.requirement(data)
        self.assertIsNone(result)  # Predicate is true for all, returns None.

    def test_some_false(self):
        """When the predicate returns False, values should be returned as
        Invalid() differences.
        """
        data = ['10', '20', 'XX']
        differences, _ = self.requirement(data)
        self.assertEqual(list(differences), [Invalid('XX')])

    def test_show_expected(self):
        data = ['XX', 'YY']
        requirement = required_predicate('YY', show_expected=True)
        differences, _ = requirement(data)
        self.assertEqual(list(differences), [Invalid('XX', expected='YY')])

    def test_duplicate_false(self):
        """Should return one difference for every false result (including
        duplicates).
        """
        data = ['10', '20', 'XX', 'XX', 'XX']  # <- Multiple XX's.
        differences, _ = self.requirement(data)
        self.assertEqual(list(differences), [Invalid('XX'), Invalid('XX'), Invalid('XX')])

    def test_empty_iterable(self):
        result = self.requirement([])
        self.assertIsNone(result)

    def test_some_false_deviations(self):
        """When the predicate returns False, values should be returned as
        Invalid() differences.
        """
        data = [10, 10, 12]
        requirement = required_predicate(10)

        differences, _ = requirement(data)
        self.assertEqual(list(differences), [Deviation(+2, 10)])

    def test_predicate_error(self):
        """Errors should not be counted as False or otherwise hidden."""
        data = ['10', '20', 'XX', 40]  # <- Predicate assumes string, int has no isdigit().
        differences, _  = self.requirement(data)
        with self.assertRaisesRegex(AttributeError, "no attribute 'isdigit'"):
            list(differences)

    def test_returned_difference(self):
        """When a predicate returns a difference object, it should
        used in place of the default Invalid difference.
        """
        def counts_to_three(x):
            if 1 <= x <= 3:
                return True
            if x == 4:
                return Invalid('4 shalt thou not count')
            return Invalid('{0} is right out'.format(x))

        requirement = required_predicate(counts_to_three)

        data = [1, 2, 3, 4, 5]
        differences, _ = requirement(data)
        expected = [
            Invalid('4 shalt thou not count'),
            Invalid('5 is right out'),
        ]
        self.assertEqual(list(differences), expected)


class TestRequiredSet(unittest.TestCase):
    def setUp(self):
        self.requirement = required_set(set([1, 2, 3]))

    def test_no_difference(self):
        data = iter([1, 2, 3])
        result = self.requirement(data)
        self.assertIsNone(result)  # No difference, returns None.

    def test_missing(self):
        data = iter([1, 2])
        differences, description = self.requirement(data)
        self.assertEqual(list(differences), [Missing(3)])

    def test_extra(self):
        data = iter([1, 2, 3, 4])
        differences, description = self.requirement(data)
        self.assertEqual(list(differences), [Extra(4)])

    def test_repeat_values(self):
        """Repeat values should not result in duplicate differences."""
        data = iter([1, 2, 3, 4, 4, 4])  # <- Multiple 4's.
        differences, description = self.requirement(data)
        self.assertEqual(list(differences), [Extra(4)])  # <- One difference.

    def test_missing_and_extra(self):
        data = iter([1, 3, 4])
        differences, description = self.requirement(data)
        self.assertEqual(list(differences), [Missing(2), Extra(4)])

    def test_empty_iterable(self):
        requirement = required_set(set([1]))
        differences, description = requirement([])
        self.assertEqual(list(differences), [Missing(1)])


class TestRequiredSequence(unittest.TestCase):
    def test_no_difference(self):
        data = ['aaa', 'bbb', 'ccc']
        required = required_sequence(['aaa', 'bbb', 'ccc'])
        self.assertIsNone(required(data))  # No difference, returns None.

    def test_some_missing(self):
        data = ['bbb', 'ddd']
        required = required_sequence(['aaa', 'bbb', 'ccc', 'ddd', 'eee'])
        differences, _ = required(data)
        expected = [
            Missing((0, 'aaa')),
            Missing((1, 'ccc')),
            Missing((2, 'eee')),
        ]
        self.assertEqual(list(differences), expected)

    def test_all_missing(self):
        data = []  # <- Empty!
        required = required_sequence(['aaa', 'bbb'])
        differences, _ = required(data)
        expected = [
            Missing((0, 'aaa')),
            Missing((0, 'bbb')),
        ]
        self.assertEqual(list(differences), expected)

    def test_some_extra(self):
        data = ['aaa', 'bbb', 'ccc', 'ddd', 'eee', 'fff']
        required = required_sequence(['aaa', 'bbb', 'ccc'])
        differences, _ = required(data)
        expected = [
            Extra((3, 'ddd')),
            Extra((4, 'eee')),
            Extra((5, 'fff')),
        ]
        self.assertEqual(list(differences), expected)

    def test_all_extra(self):
        data = ['aaa', 'bbb']
        required = required_sequence([])  # <- Empty!
        differences, _ = required(data)
        expected = [
            Extra((0, 'aaa')),
            Extra((1, 'bbb')),
        ]
        self.assertEqual(list(differences), expected)

    def test_one_missing_and_extra(self):
        data = ['aaa', 'xxx', 'ccc']
        required = required_sequence(['aaa', 'bbb', 'ccc'])
        differences, _ = required(data)
        expected = [
            Missing((1, 'bbb')),
            Extra((1, 'xxx')),
        ]
        self.assertEqual(list(differences), expected)

    def test_some_missing_and_extra(self):
        data = ['aaa', 'xxx', 'ccc', 'yyy', 'zzz']
        required = required_sequence(['aaa', 'bbb', 'ccc', 'ddd', 'eee'])
        differences, _ = required(data)
        expected = [
            Missing((1, 'bbb')),
            Extra((1, 'xxx')),
            Missing((3, 'ddd')),
            Extra((3, 'yyy')),
            Missing((4, 'eee')),
            Extra((4, 'zzz')),
        ]
        self.assertEqual(list(differences), expected)

    def test_some_missing_and_extra_different_lengths(self):
        data = ['aaa', 'xxx', 'eee']
        required = required_sequence(['aaa', 'bbb', 'ccc', 'ddd', 'eee'])
        differences, _ = required(data)
        expected = [
            Missing((1, 'bbb')),
            Extra((1, 'xxx')),
            Missing((2, 'ccc')),
            Missing((2, 'ddd')),
        ]
        self.assertEqual(list(differences), expected)

        data = ['aaa', 'xxx', 'yyy', 'zzz', 'ccc']
        required = required_sequence(['aaa', 'bbb', 'ccc'])
        differences, _ = required(data)
        expected = [
            Missing((1, 'bbb')),
            Extra((1, 'xxx')),
            Extra((2, 'yyy')),
            Extra((3, 'zzz')),
        ]
        self.assertEqual(list(differences), expected)

    def test_numeric_matching(self):
        """When checking sequence order, numeric differences should NOT
        be converted into Deviation objects.
        """
        data = [1, 100, 4, 200, 300]
        required = required_sequence([1, 2, 3, 4, 5])
        differences, _ = required(data)
        expected = [
            Missing((1, 2)),
            Extra((1, 100)),
            Missing((2, 3)),
            Missing((3, 5)),
            Extra((3, 200)),
            Extra((4, 300)),
        ]
        self.assertEqual(list(differences), expected)

    def test_unhashable_objects(self):
        """Should try to compare sequences of unhashable types."""
        data = [{'a': 1}, {'b': 2}, {'c': 3}]
        required = required_sequence([{'a': 1}, {'b': 2}, {'c': 3}])
        result = required(data)
        self.assertIsNone(result)  # No difference, returns None.

        data = [{'a': 1}, {'x': 0}, {'d': 4}, {'y': 5}, {'g': 7}]
        required = required_sequence([{'a': 1}, {'b': 2}, {'c': 3}, {'d': 4}, {'f': 6}])
        differences, _ = required(data)
        expected = [
            Missing((1, {'b': 2})),
            Extra((1, {'x': 0})),
            Missing((2, {'c': 3})),
            Missing((3, {'f': 6})),
            Extra((3, {'y': 5})),
            Extra((4, {'g': 7})),
        ]
        self.assertEqual(list(differences), expected)


class TestGetGroupRequirement(unittest.TestCase):
    def test_set(self):
        requirement = _get_group_requirement(set(['foo']))
        self.assertTrue(requirement._group_requirement)

    def test_predicate(self):
        requirement = _get_group_requirement('foo')
        self.assertTrue(requirement._group_requirement)

        requirement = _get_group_requirement('bar', show_expected=True)
        self.assertTrue(requirement._group_requirement)

    def test_sequence(self):  # For base-item sequences.
        requirement = _get_group_requirement(['foo'])
        self.assertTrue(requirement._group_requirement)

    def test_already_requirement(self):
        """If the requirement is already a group requirement, then the
        original object should be returned.
        """
        requirement1 = _get_group_requirement('foo')
        requirement2 = _get_group_requirement(requirement1)
        self.assertIs(requirement1, requirement2)


class TestDataVsRequirement(unittest.TestCase):
    def test_set_against_container(self):
        requirement = set(['foo'])

        result = _data_vs_requirement(['foo', 'foo'], requirement)
        self.assertIsNone(result)

        differences, _ = _data_vs_requirement(['foo', 'bar'], requirement)
        self.assertEqual(list(differences), [Extra('bar')])

    def test_set_against_single_item(self):
        requirement = set(['foo'])
        result = _data_vs_requirement('foo', requirement)
        self.assertIsNone(result)

        requirement = set(['foo', 'bar'])
        differences, _ = _data_vs_requirement('bar', requirement)
        self.assertEqual(differences, Missing('foo'), msg='should not be in container')

        requirement = set(['foo'])
        differences, _ = _data_vs_requirement('bar', requirement)
        differences = list(differences)
        self.assertEqual(len(differences), 2, msg='expects container if multiple diffs')
        self.assertIn(Missing('foo'), differences)
        self.assertIn(Extra('bar'), differences)

    def test_predicate_against_container(self):
        requirement = 'foo'
        result = _data_vs_requirement(['foo', 'foo'], requirement)
        self.assertIsNone(result)

        requirement = 'foo'
        differences, _ = _data_vs_requirement(['foo', 'bar'], requirement)
        self.assertEqual(list(differences), [Invalid('bar')], msg='should be iterable of diffs')

        requirement = 10
        differences, _ = _data_vs_requirement([10, 12], requirement)
        self.assertEqual(list(differences), [Deviation(+2, 10)], msg='should be iterable of diffs')

        requirement = (1, 'j')
        differences, _ = _data_vs_requirement([(1, 'x'), (1, 'j')], requirement)
        self.assertEqual(list(differences), [Invalid((1, 'x'))], msg='should be iterable of diffs and no "expected"')

    def test_predicate_against_single_item(self):
        requirement = 'foo'
        result = _data_vs_requirement('foo', requirement)
        self.assertIsNone(result)

        requirement = 'foo'
        differences, _ = _data_vs_requirement('bar', requirement)
        self.assertEqual(differences, Invalid('bar', expected='foo'), msg='should have no container and include "expected"')

        requirement = 10
        differences, _ = _data_vs_requirement(12, requirement)
        self.assertEqual(differences, Deviation(+2, 10), msg='should have no container')

        requirement = (1, 'j')
        differences, _ = _data_vs_requirement((1, 'x'), requirement)
        self.assertEqual(differences, Invalid((1, 'x'), expected=(1, 'j')), msg='should have no container and include "expected"')

    def test_description_message(self):
        # Requirement returns differences and description.
        @group_requirement
        def require1(iterable):
            return [Invalid('bar')], 'some message'

        _, description = _data_vs_requirement('bar', require1)
        self.assertEqual(description, 'some message')

        # Requirement returns differences only, should get default description.
        @group_requirement
        def require2(iterable):
            return [Invalid('bar')]

        _, description = _data_vs_requirement('bar', require2)
        self.assertEqual(description, 'does not satisfy require2()')


class TestDatadictVsRequirement(unittest.TestCase):
    @staticmethod
    def evaluate_generators(dic):
        new_dic = dict()
        for k, v in dic.items():
            new_dic[k] = list(v) if isinstance(v, Iterator) else v
        return new_dic

    def test_no_differences(self):
        # Set membership.
        data = {'a': ['x', 'y'], 'b': ['x', 'y'],}
        requirement = set(['x', 'y'])
        result = _datadict_vs_requirement(data, requirement)
        self.assertIsNone(result)

        # Equality of single value.
        data = {'a': 'x', 'b': 'x'}
        requirement = 'x'
        result = _datadict_vs_requirement(data, requirement)
        self.assertIsNone(result)

    def test_set_membership(self):
        data = {'a': ['x', 'x'], 'b': ['x', 'y', 'z']}
        requirement = set(['x', 'y'])
        differences, description = _datadict_vs_requirement(data, requirement)
        differences = self.evaluate_generators(differences)
        expected = {'a': [Missing('y')], 'b': [Extra('z')]}
        self.assertEqual(differences, expected)
        self.assertEqual(description, 'does not satisfy set membership')

    def test_predicate_with_single_item_values(self):
        data = {'a': 'x', 'b': 10, 'c': 9}
        requirement = 9
        differences, description = _datadict_vs_requirement(data, requirement)
        expected = {'a': Invalid('x'), 'b': Deviation(+1, 9)}
        self.assertEqual(differences, expected)

    def test_predicate_with_lists_of_values(self):
        data = {'a': ['x', 'j'], 'b': [10, 9], 'c': [9, 9]}
        requirement = 9
        differences, description = _datadict_vs_requirement(data, requirement)
        differences = self.evaluate_generators(differences)
        expected = {'a': [Invalid('x'), Invalid('j')], 'b': [Deviation(+1, 9)]}
        self.assertEqual(differences, expected)

    def test_tuple_with_single_item_values(self):
        data = {'a': ('x', 1.0), 'b': ('y', 2), 'c': ('x', 3)}
        required = ('x', int)
        differences, description = _datadict_vs_requirement(data, required)
        expected = {'a': Invalid(('x', 1.0)), 'b': Invalid(('y', 2))}
        self.assertEqual(differences, expected)

    def test_tuple_with_lists_of_values(self):
        data = {'a': [('x', 1.0), ('x', 1)], 'b': [('y', 2), ('x', 3)]}
        required = ('x', int)
        differences, description = _datadict_vs_requirement(data, required)
        differences = self.evaluate_generators(differences)
        expected = {'a': [Invalid(('x', 1.0))], 'b': [Invalid(('y', 2))]}
        self.assertEqual(differences, expected)

    def test_description_message(self):
        data = {'a': 'bar', 'b': ['bar', 'bar']}

        # When message is the same for all items, use provided message.
        @group_requirement
        def requirement1(iterable):
            iterable = list(iterable)
            return [Invalid('bar')], 'got some items'

        _, description = _datadict_vs_requirement(data, requirement1)
        self.assertEqual(description, 'got some items')

        # When messages are different, description should be None.
        @group_requirement
        def requirement2(iterable):
            iterable = list(iterable)
            return [Invalid('bar')], 'got {0} items'.format(len(iterable))

        _, description = _datadict_vs_requirement(data, requirement2)
        self.assertIsNone(description)


class TestDatadictVsRequirementdict(unittest.TestCase):
    """Calling _apply_mapping_to_mapping() should run the appropriate
    comparison function (internally) for each value-group and
    return the results as an iterable of key-value items.
    """
    @staticmethod
    def evaluate_generators(dic):
        new_dic = dict()
        for k, v in dic.items():
            new_dic[k] = list(v) if isinstance(v, Iterator) else v
        return new_dic

    def test_no_differences(self):
        # Set membership.
        data = {'a': ['x', 'y']}
        result = _datadict_vs_requirementdict(data, {'a': set(['x', 'y'])})
        self.assertIsNone(result)

        # Equality of single values.
        data = {'a': 'x', 'b': 'y'}
        result = _datadict_vs_requirementdict(data, {'a': 'x', 'b': 'y'})
        self.assertIsNone(result)

    def test_bad_data_type(self):
        not_a_mapping = 'abc'
        a_mapping = {'a': 'abc'}

        with self.assertRaises(TypeError):
            _datadict_vs_requirementdict(not_a_mapping, a_mapping)

    def test_set_membership_differences(self):
        differences, _ = _datadict_vs_requirementdict(
            {'a': ['x', 'x'], 'b': ['x', 'y', 'z']},
            {'a': set(['x', 'y']), 'b': set(['x', 'y'])},
        )
        differences = self.evaluate_generators(differences)
        expected = {'a': [Missing('y')], 'b': [Extra('z')]}
        self.assertEqual(differences, expected)

    def test_equality_of_single_values(self):
        differences, _ = _datadict_vs_requirementdict(
            data={'a': 'x', 'b': 10},
            requirement={'a': 'j', 'b': 9},
        )
        expected = {'a': Invalid('x', expected='j'), 'b': Deviation(+1, 9)}
        self.assertEqual(differences, expected)

        differences, _ = _datadict_vs_requirementdict(
            data={'a': 'x', 'b': 10, 'c': 10},
            requirement={'a': 'j', 'b': 'k', 'c': 9},
        )
        expected = {'a': Invalid('x', 'j'), 'b': Invalid(10, 'k'), 'c': Deviation(+1, 9)}
        self.assertEqual(differences, expected)

    def test_equality_of_multiple_values(self):
        differences, _ = _datadict_vs_requirementdict(
            data={'a': ['x', 'j'], 'b': [10, 9]},
            requirement={'a': 'j', 'b': 9},
        )
        differences = self.evaluate_generators(differences)
        expected = {'a': [Invalid('x')], 'b': [Deviation(+1, 9)]}
        self.assertEqual(differences, expected)

    def test_equality_of_single_tuples(self):
        differences, _ = _datadict_vs_requirementdict(
            data={'a': (1, 'x'), 'b': (9, 10)},
            requirement={'a': (1, 'j'), 'b': (9, 9)},
        )
        expected = {'a': Invalid((1, 'x'), expected=(1, 'j')),
                    'b': Invalid((9, 10), expected=(9, 9))}
        self.assertEqual(differences, expected)

    def test_equality_of_multiple_tuples(self):
        differences, _ = _datadict_vs_requirementdict(
            data={'a': [(1, 'j'), (1, 'x')], 'b': [(9, 9), (9, 10)]},
            requirement={'a': (1, 'j'), 'b': (9, 9)},
        )
        differences = self.evaluate_generators(differences)
        expected = {'a': [Invalid((1, 'x'))],
                    'b': [Invalid((9, 10))]}
        self.assertEqual(differences, expected)

    def test_missing_keys(self):
        # Equality of multiple values, missing key with single item.
        differences, _ = _datadict_vs_requirementdict(
            data={'a': ['x', 'j'], 'b': [10, 9]},
            requirement={'a': 'j', 'b': 9, 'c': 'z'},
        )
        differences = self.evaluate_generators(differences)
        expected = {'a': [Invalid('x')], 'b': [Deviation(+1, 9)], 'c': Missing('z')}
        self.assertEqual(differences, expected)

        # Equality of multiple values, missing key with single item.
        differences, _ = _datadict_vs_requirementdict(
            data={'a': ['x', 'j'], 'b': [10, 9], 'c': 'z'},
            requirement={'a': 'j', 'b': 9},
        )
        differences = self.evaluate_generators(differences)
        expected = {'a': [Invalid('x')], 'b': [Deviation(+1, 9)], 'c': Extra('z')}
        self.assertEqual(differences, expected)

        # Missing key, set membership.
        differences, _ = _datadict_vs_requirementdict(
            data={'a': 'x'},
            requirement={'a': 'x', 'b': set(['z'])},
        )
        differences = self.evaluate_generators(differences)
        expected = {'b': [Missing('z')]}
        self.assertEqual(differences, expected)

    def test_mismatched_keys(self):
        # Mapping of single-items (BaseElement objects).
        differences, _ = _datadict_vs_requirementdict(
            data={'a': ('abc', 1), 'c': ('abc', 2.0)},
            requirement={'a': ('abc', int), 'b': ('abc', float)},
        )
        expected = {
            'b': Missing(('abc', float)),
            'c': Extra(('abc', 2.0)),
        }
        self.assertEqual(differences, expected)

        # Mapping of containers (lists of BaseElement objects).
        differences, _ = _datadict_vs_requirementdict(
            data={
                'a': [('abc', 1), ('abc', 2)],
                'c': [('abc', 1.0), ('abc', 2.0)],
            },
            requirement={'a': ('abc', int), 'b': ('abc', float)},
        )
        differences = self.evaluate_generators(differences)
        expected = {
            'c': [Extra(('abc', 1.0)), Extra(('abc', 2.0))],
            'b': Missing(('abc', float)),
        }
        self.assertEqual(differences, expected)

    def test_empty_vs_nonempty_values(self):
        empty = {}
        nonempty = {'a': set(['x'])}

        result = _datadict_vs_requirementdict(empty, empty)
        self.assertIsNone(result)

        differences, _ = _datadict_vs_requirementdict(nonempty, empty)
        differences = self.evaluate_generators(differences)
        self.assertEqual(differences, {'a': [Extra('x')]})

        differences, _ = _datadict_vs_requirementdict(empty, nonempty)
        differences = self.evaluate_generators(differences)
        self.assertEqual(differences, {'a': [Missing('x')]})

    def test_description_message(self):
        data = {'a': 'bar', 'b': ['bar', 'bar']}

        @group_requirement
        def func1(iterable):
            return [Invalid('bar')], 'some message'

        @group_requirement
        def func2(iterable):
            return [Invalid('bar')], 'some other message'

        # When message is same for all items, use provided message.
        requirement1 = {'a': func1, 'b': func1}
        _, description = _datadict_vs_requirementdict(data, requirement1)
        self.assertEqual(description, 'some message')

        # When messages are different, description should be None.
        requirement2 = {'a': func1, 'b': func2}
        _, description = _datadict_vs_requirementdict(data, requirement2)
        self.assertIsNone(description)


class TestBaseRequirement(unittest.TestCase):
    def setUp(self):
        class MinimalRequirement(BaseRequirement):
            def check_data(self, data):
                return [], ''

        self.requirement = MinimalRequirement()

    def test_missing_abstractmethod(self):
        with self.assertRaises(TypeError):
            BaseRequirement()

    def test_verify_difference(self):
        self.assertIsNone(self.requirement._verify_difference(Missing(1)),
                          msg='no explicit return value')

        regex = (r"values returned from MinimalRequirement must be "
                 r"difference objects, got str: 'a string instance'")
        with self.assertRaisesRegex(TypeError, regex):
            self.requirement._verify_difference('a string instance')

    def test_wrap_difference_group(self):
        group = [Missing(1), Missing(2)]
        wrapped = self.requirement._wrap_difference_group(group)
        self.assertEqual(list(wrapped), group)

        group = [Missing(1), 'a string instance']
        wrapped = self.requirement._wrap_difference_group(group)
        with self.assertRaises(TypeError):
            list(wrapped)  # <- Evaluate generator.

    def test_wrap_difference_items(self):
        # Values as single differences.
        items = [('A', Missing(1)), ('B', Missing(2))]
        wrapped = self.requirement._wrap_difference_items(items)
        self.assertEqual(list(wrapped), items)

        items = [('A', Missing(1)), ('B', 'a string instance')]
        wrapped = self.requirement._wrap_difference_items(items)
        with self.assertRaises(TypeError):
            list(wrapped)  # <- Evaluate generator.

        # Values as groups of differences.
        items = [('A', [Missing(1), Missing(2)]),
                 ('B', [Missing(3), Missing(4)])]
        wrapped = self.requirement._wrap_difference_items(items)
        self.assertEqual([(k, list(v)) for k, v in wrapped], items)

        items = [('A', [Missing(1), Missing(2)]),
                 ('B', [Missing(3), 'a string instance'])]
        wrapped = self.requirement._wrap_difference_items(items)
        with self.assertRaises(TypeError):
            [(k, list(v)) for k, v in wrapped]  # <- Evaluate generator.

    def test_normalize_iter_and_description(self):
        result = ([Missing(1)], 'error message')  # <- Iterable and description.
        diffs, desc = self.requirement._normalize(result)
        self.assertEqual(list(diffs), [Missing(1)])
        self.assertEqual(desc, 'error message')

    def test_normalize_iter(self):
        result = [Missing(1)]  # <- Iterable only, no description.
        diffs, desc = self.requirement._normalize(result)
        self.assertEqual(list(diffs), [Missing(1)])
        self.assertEqual(desc, 'does not satisfy MinimalRequirement', msg='gets default description')

    def test_normalize_tuple_of_diffs(self):
        """Should not mistake a 2-tuple of difference objects for a
        2-tuple containing an iterable of differences with a string
        description.
        """
        result = (Missing(1), Missing(2))  # <- A 2-tuple of diffs.
        diffs, desc = self.requirement._normalize(result)
        self.assertEqual(list(diffs), [Missing(1), Missing(2)])
        self.assertEqual(desc, 'does not satisfy MinimalRequirement', msg='gets default description')

    def test_normalize_empty_iter(self):
        """Empty iterable result should be converted to None."""
        result = (iter([]), 'error message')  # <- Empty iterable and description.
        normalized = self.requirement._normalize(result)
        self.assertIsNone(normalized)

        result = iter([])  # <- Empty iterable
        normalized = self.requirement._normalize(result)
        self.assertIsNone(normalized)

    def test_normalize_bad_types(self):
        """Bad return types should trigger TypeError."""
        with self.assertRaisesRegex(TypeError, 'should return .* iterable'):
            result = (Missing(1), 'error message')  # <- Non-iterable and description.
            self.requirement._normalize(result)

        with self.assertRaisesRegex(TypeError, 'should return .* iterable'):
            result = None  # <- None only.
            self.requirement._normalize(result)

        with self.assertRaisesRegex(TypeError, 'should return .* an iterable and a string'):
            result = (None, 'error message')  # <- None and description
            self.requirement._normalize(result)


class TestRequiredItems(unittest.TestCase):
    def test_missing_abstractmethod(self):
        with self.assertRaises(TypeError):
            RequiredItems()

    def test_check_items(self):
        class RequiredIntValues(RequiredItems):
            def check_items(self, items):
                for k, v in items:
                    if not isinstance(v, int):
                        yield k, Invalid(v)

        requirement = RequiredIntValues()

        self.assertIsNone(requirement([('A', 1), ('B', 2)]),
                          msg='should return None when data satisfies requirement')

        differences, description = requirement([('A', 1), ('B', 2.0)])
        self.assertEqual(list(differences), [('B', Invalid(2.0))],
                         msg='should return items iterable for values that fail requirement')


class TestRequiredGroup(unittest.TestCase):
    def setUp(self):
        class RequiredThreePlus(RequiredGroup):
            def check_group(self, group):
                group = list(group)
                if len(group) < 3:
                    diffs = (Invalid(x) for x in group)
                    return diffs, 'requires 3 or more elements'
                return [], ''

        self.requirement = RequiredThreePlus()

    def test_missing_abstractmethod(self):
        with self.assertRaises(TypeError):
            RequiredGroup()

    def test_check_group(self):
        requirement = self.requirement

        diff, desc = requirement.check_group([1, 2, 3])
        self.assertEqual(list(diff), [])
        self.assertEqual(desc, '')

        diff, desc = requirement.check_group([1, 2])
        self.assertEqual(list(diff), [Invalid(1), Invalid(2)])
        self.assertEqual(desc, 'requires 3 or more elements')

    def test_check_items(self):
        data = [('A', [1, 2, 3]), ('B', [4, 5, 6])]
        diff, desc = self.requirement.check_items(data)
        self.assertEqual(diff, [])
        self.assertEqual(desc, '')

        data = [('A', [1, 2, 3]), ('B', [4, 5])]
        diff, desc = self.requirement.check_items(data)
        diff = [(k, list(v)) for k, v in diff]
        self.assertEqual(diff, [('B', [Invalid(4), Invalid(5)])])
        self.assertEqual(desc, 'requires 3 or more elements')

    def test_check_data(self):
        # Test mapping or key/value items.
        data = {'A': [1, 2, 3], 'B': [4, 5], 'C': 6}
        diff, desc = self.requirement.check_data(data)
        diff = [(k, list(v)) for k, v in diff]
        self.assertEqual(diff, [('B', [Invalid(4), Invalid(5)]), ('C', [Invalid(6)])])
        self.assertEqual(desc, 'requires 3 or more elements')

        # Test group.
        data = [4, 5]
        diff, desc = self.requirement.check_data(data)
        self.assertEqual(list(diff), [Invalid(4), Invalid(5)])
        self.assertEqual(desc, 'requires 3 or more elements')

        # Test BaseElement.
        data = 4
        diff, desc = self.requirement.check_data(data)
        self.assertEqual(list(diff), [Invalid(4)])
        self.assertEqual(desc, 'requires 3 or more elements')
