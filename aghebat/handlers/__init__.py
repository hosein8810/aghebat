"""ثبت همه روترهای بات عاقبت."""
from __future__ import annotations

from aiogram import Router

from . import admin, ads, botadmin, common, daily, fun, group, owner, profile, tasks


def build_router() -> Router:
    """روتر اصلی با ترتیب درست هندلرها."""
    router = Router(name="aghebat")
    router.include_router(common.router)
    router.include_router(daily.router)
    router.include_router(profile.router)
    router.include_router(tasks.router)
    router.include_router(admin.router)
    router.include_router(owner.router)
    router.include_router(botadmin.router)
    router.include_router(ads.router)
    router.include_router(fun.router)
    router.include_router(group.router)
    return router
