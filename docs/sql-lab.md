# SQL Lab

Kardo includes an optional SQL practice module: 151 exercises in 13 tracks, checked instantly against a realistic
practice database. Open it from the database icon on the home screen. If you only want flashcards, ignore it; it
takes no space in your collection.

## Tracks

1. Foundations
2. NULLs and CASE
3. Joins
4. Aggregation
5. Subqueries and sets
6. CTEs
7. Recursive CTEs
8. Window functions
9. Dates, strings and cleaning
10. Changing data (INSERT, UPDATE, DELETE, DDL)
11. Analytics patterns
12. Analytics engineering (dbt style)
13. Performance (indexes, `EXPLAIN QUERY PLAN`)

## The practice database

*Shopwise* is a fictional online shop: categories, products, customers, employees, orders, order items, payments,
subscriptions, web events, daily logins, segment changes and a deliberately messy raw CRM table for cleaning exercises. It's generated from a fixed seed when the server starts, so everyone gets identical data
and the answers stay correct. Browse the tables from **Tables** in the lab.

## How queries run

- Every query runs in a **fresh in-memory copy** of the practice database. `DROP TABLE orders` is safe; the next query starts clean.
- A query may run for up to 4 seconds; up to 500 rows are shown.
- `ATTACH`, `load_extension` and non-read-only `PRAGMA`s are blocked. The lab never touches your flashcard database.
- **Explain** shows the query plan instead of the result.
- The **Sandbox** is a free editor with no exercise attached.

## How answers are checked

Your result is compared with the reference solution's result:

- Column **names** don't matter; column **order** and values do.
- Row order matters only when the exercise asks for an ordering.
- Numbers are compared with a small tolerance (0.01).
- For exercises that change data, a hidden check query runs after your statements and its result is compared.

When an answer is wrong, the message says how: wrong number of columns or rows, right rows in the wrong order, or
which columns differ.

## Adding exercises

Exercises live in [`lab_exercises.txt`](../lab_exercises.txt):

```text
=== j14 | 03 Joins | Customers without orders
Return the `customer_id` and `email` of customers who have never placed an order.
--- hint
A LEFT JOIN plus `WHERE o.order_id IS NULL`, or NOT EXISTS.
--- solution
SELECT c.customer_id, c.email
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

Optional sections: `--- check` (a query run after the learner's statements, for DML/DDL tasks), `--- setup` (run
first for both learner and solution) and `--- options` containing `ordered` (row order must match).

Ids must be unique. Run the tests afterwards: they verify that every reference solution passes its own check.
