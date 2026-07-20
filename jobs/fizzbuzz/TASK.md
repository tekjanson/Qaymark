# Job: FizzBuzz

Implement classic FizzBuzz as a single pure function in a single file
`fizzbuzz.py` at the workspace root. The fixed acceptance tests live in
`test_fizzbuzz.py` (you may not edit them). Run them with
`python3 -m unittest test_fizzbuzz`.

## Public API

Define one function:

- `fizzbuzz(n)` — return a **list** of length `n` describing the numbers `1`
  through `n` (inclusive), in order:
  - a multiple of both 3 and 5 becomes the string `"FizzBuzz"`,
  - a multiple of only 3 becomes `"Fizz"`,
  - a multiple of only 5 becomes `"Buzz"`,
  - any other number `i` becomes its decimal string, e.g. `str(i)`.

`fizzbuzz(0)` returns an empty list. Assume `n >= 0`.

## Acceptance

Validate with:

```bash
python3 -m unittest test_fizzbuzz
```

## Style constraints

Everything must pass the strict slop-be-gone gate: keep functions small (≤ 45
lines, ≤ 5 arguments), keep lines at or under 100 characters, end the file with
a single newline, use no placeholder comments, and do not use `eval`.
