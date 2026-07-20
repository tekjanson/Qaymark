"""Fixed acceptance tests for FizzBuzz. This is the spec; do not edit it.

The harness must make fizzbuzz.py pass these tests.
"""

import unittest

from fizzbuzz import fizzbuzz


class FizzBuzzTests(unittest.TestCase):
    def test_empty_for_zero(self):
        self.assertEqual(fizzbuzz(0), [])

    def test_length_matches_n(self):
        self.assertEqual(len(fizzbuzz(20)), 20)

    def test_plain_numbers_are_strings(self):
        self.assertEqual(fizzbuzz(2), ["1", "2"])

    def test_fizz_on_three(self):
        self.assertEqual(fizzbuzz(3)[2], "Fizz")

    def test_buzz_on_five(self):
        self.assertEqual(fizzbuzz(5)[4], "Buzz")

    def test_fizzbuzz_on_fifteen(self):
        self.assertEqual(fizzbuzz(15)[14], "FizzBuzz")

    def test_first_fifteen_sequence(self):
        expected = [
            "1", "2", "Fizz", "4", "Buzz", "Fizz", "7", "8", "Fizz", "Buzz",
            "11", "Fizz", "13", "14", "FizzBuzz",
        ]
        self.assertEqual(fizzbuzz(15), expected)


if __name__ == "__main__":
    unittest.main()
