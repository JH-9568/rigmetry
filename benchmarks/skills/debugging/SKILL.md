# Focused Debugging Workflow

1. Read the implementation and focused tests before editing.
2. Run the focused test suite once to reproduce the failure.
3. State the smallest behavioral mismatch supported by the failure.
4. Change only the implementation needed for that mismatch; do not weaken or rewrite tests.
5. Run the same focused test suite again and inspect its exit status before finishing.
