"""ثبت همه روترهای بات عاقبت."""
from __future__ import annotations

from aiogram import Router

from . import (
    admin,
    ads,
    botadmin,
    common,
    config_io,
    daily,
    fun,
    group,
    market,
    owner,
    panels,
    profile,
    tasks,
    tictactoe,
)


def build_router() -> Router:
    """روتر اصلی با ترتیب درست هندلرها."""
    router = Router(name="aghebat")
    router.include_router(common.router)
    router.include_router(panels.router)
    router.include_router(config_io.router)
    router.include_router(daily.router)
    router.include_router(profile.router)
    router.include_router(tasks.router)
    router.include_router(admin.router)
    router.include_router(owner.router)
    router.include_router(botadmin.router)
    router.include_router(ads.router)
    router.include_router(market.router)
    router.include_router(tictactoe.router)
    router.include_router(fun.router)
    router.include_router(group.router)
    return router
