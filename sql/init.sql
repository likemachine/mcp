BEGIN;

CREATE TABLE public.clients (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    email text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL
);

CREATE TABLE public.products (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    category text NOT NULL,
    price numeric(12, 2) NOT NULL CHECK (price >= 0)
);

CREATE TABLE public.orders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id bigint NOT NULL REFERENCES public.clients(id),
    created_at timestamptz NOT NULL,
    status text NOT NULL
        CHECK (status IN ('new', 'paid', 'shipped', 'cancelled'))
);

CREATE TABLE public.order_items (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL REFERENCES public.orders(id),
    product_id bigint NOT NULL REFERENCES public.products(id),
    quantity integer NOT NULL CHECK (quantity > 0),
    price numeric(12, 2) NOT NULL CHECK (price >= 0)
);

CREATE INDEX idx_orders_client_id
    ON public.orders(client_id);

CREATE INDEX idx_orders_created_at
    ON public.orders(created_at);

CREATE INDEX idx_order_items_order_id
    ON public.order_items(order_id);

CREATE INDEX idx_order_items_product_id
    ON public.order_items(product_id);

INSERT INTO public.clients (name, email, created_at)
SELECT
    'Client ' || g,
    'client' || g || '@example.com',
    TIMESTAMPTZ '2025-01-01 00:00:00+00'
        + g * INTERVAL '1 day'
FROM generate_series(1, 20) AS s(g)
ORDER BY g;

INSERT INTO public.products (name, category, price)
SELECT
    'Product ' || g,
    (ARRAY['electronics', 'home', 'sports'])[((g - 1) % 3) + 1],
    (250 + g * 175.50)::numeric(12, 2)
FROM generate_series(1, 15) AS s(g)
ORDER BY g;

INSERT INTO public.orders (client_id, created_at, status)
SELECT
    ((g * 7 - 1) % 20) + 1,
    TIMESTAMPTZ '2025-03-01 00:00:00+00'
        + ((g - 1) % 180) * INTERVAL '1 day'
        + (g % 24) * INTERVAL '1 hour',
    (ARRAY['new', 'paid', 'shipped', 'cancelled'])[
        (((g - 1) / 7) % 4) + 1
    ]
FROM generate_series(1, 200) AS s(g)
ORDER BY g;

INSERT INTO public.order_items (
    order_id, product_id, quantity, price
)
SELECT
    ((g - 1) % 200) + 1,
    p.id,
    ((g - 1) % 4) + 1,
    p.price
FROM generate_series(1, 500) AS s(g)
JOIN public.products AS p
    ON p.id = ((g - 1) % 15) + 1
ORDER BY g;

GRANT USAGE ON SCHEMA public TO mcp_readonly;

GRANT SELECT ON
    public.clients,
    public.products,
    public.orders,
    public.order_items
TO mcp_readonly;

ANALYZE public.clients;
ANALYZE public.products;
ANALYZE public.orders;
ANALYZE public.order_items;

COMMIT;
