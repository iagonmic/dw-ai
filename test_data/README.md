# DW-AI Test Data

These small CSV datasets are meant for local demos when users do not have their own enterprise data yet. Each table has 20 rows or fewer to keep the repository light.

## easy_retail

Clear star-schema pattern:

- Facts expected: `orders` and/or `order_items`
- Dimensions expected: `customers`, `products`, `stores`, `employees`, `date`
- Strong keys: `customer_id`, `product_id`, `store_id`, `employee_id`, `order_id`

## medium_university

English university pattern inspired by academic administrative systems:

- Facts expected: `enrollments`
- Dimensions expected: `students`, `course_components`, `instructors`, `date`
- Temporal columns: `year`, `term`, `entry_year`, `entry_term`, `enrollment_date`
- Keys: `student_id`, `course_component_id`, `instructor_id`, `course_id`

## hard_healthcare

Harder enterprise pattern with several plausible modelling choices:

- Facts expected: `encounters`, `lab_results`, `medication_orders`, `claims`
- Dimensions expected: `patients`, `providers`, `departments`, `diagnoses`, `procedures`, `date`
- Challenges: multiple events per patient, several dates per fact, mixed billing/clinical measures, and bridge-like diagnosis/procedure relationships.

Upload one folder at a time in the Streamlit app for the clearest results.
