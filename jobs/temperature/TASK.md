# Job: Temperature conversion

Implement two small pure functions in a single file `temperature.py` at the
workspace root. The fixed acceptance tests live in `test_temperature.py` (you
may not edit them). Run them with `python3 -m unittest test_temperature`.

## Public API

Define exactly two functions:

- `c_to_f(celsius)` — convert Celsius to Fahrenheit: `celsius * 9 / 5 + 32`.
- `f_to_c(fahrenheit)` — convert Fahrenheit to Celsius: `(fahrenheit - 32) * 5 / 9`.

Both accept and return floats (ints are fine as input). Do not round.

## Acceptance

Validate with:

```bash
python3 -m unittest test_temperature
```

## Style constraints

Everything must pass the strict slop-be-gone gate: keep functions small (≤ 45
lines, ≤ 5 arguments), keep lines at or under 100 characters, end the file with
a single newline, use no placeholder comments, and do not use `eval`.
