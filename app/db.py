from contextvars import ContextVar


# D1 database binding for the current Worker invocation.
_d1 = ContextVar("d1", default=None)


def configure_d1(database):
    """
    Передаёт D1 binding в слой базы данных.
    Вызывается из worker.py перед обработкой запроса.
    """
    _d1.set(database)


def get_d1():
    database = _d1.get()

    if database is None:
        raise RuntimeError(
            "D1 database is not configured. "
            "Call configure_d1(env.DB) first."
        )

    return database


async def fetch_one(
    query: str,
    *params,
):
    result = await (
        get_d1()
        .prepare(query)
        .bind(*params)
        .first()
    )

    return result


async def fetch_value(
    query: str,
    *params,
):
    result = await (
        get_d1()
        .prepare(query)
        .bind(*params)
        .first()
    )

    if result is None:
        return None

    if isinstance(result, dict):
        return next(iter(result.values()), None)

    return result


async def fetch_all(
    query: str,
    *params,
):
    result = await (
        get_d1()
        .prepare(query)
        .bind(*params)
        .all()
    )

    return result.results


async def execute(
    query: str,
    *params,
):
    return await (
        get_d1()
        .prepare(query)
        .bind(*params)
        .run()
    )


async def execute_many(
    statements: list[tuple[str, tuple]],
):
    database = get_d1()

    prepared = [
        database.prepare(query).bind(*params)
        for query, params in statements
    ]

    return await database.batch(prepared)
