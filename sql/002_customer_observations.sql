BEGIN;

CREATE TABLE public.customer_observations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id text,
    observation_date date,
    region text,
    category text,
    segment text,
    age integer,
    monthly_income numeric,
    monthly_expenses numeric,
    orders_count integer,
    churn smallint
);

GRANT SELECT ON public.customer_observations TO mcp_readonly;

COMMIT;
