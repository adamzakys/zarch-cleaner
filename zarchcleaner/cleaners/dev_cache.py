"""Caches produced by development tooling."""

from __future__ import annotations

import os
from pathlib import Path

from ..models import CleanItem, Risk
from .base import Cleaner


class _DevCache:
    __slots__ = ("item_id", "title", "path", "description", "risk", "enabled_default")

    def __init__(
        self,
        item_id: str,
        title: str,
        path: str,
        description: str,
        risk: Risk = Risk.SAFE,
        enabled_default: bool = True,
    ) -> None:
        self.item_id = item_id
        self.title = title
        self.path = path
        self.description = description
        self.risk = risk
        self.enabled_default = enabled_default


DEV_CACHES: tuple[_DevCache, ...] = (
    _DevCache(
        "npm-cacache",
        "Cache paket npm",
        "~/.npm/_cacache",
        "Cache paket npm. Setara dengan `npm cache clean --force`.",
    ),
    _DevCache(
        "npm-npx",
        "Cache paket npx",
        "~/.npm/_npx",
        "Paket yang pernah dijalankan lewat npx. npx akan mengunduh ulang saat "
        "diperlukan.",
    ),
    _DevCache(
        "pip",
        "Cache pip",
        "~/.cache/pip",
        "Cache wheel dan unduhan HTTP pip. Setara dengan `pip cache purge`.",
    ),
    _DevCache(
        "uv",
        "Cache uv",
        "~/.cache/uv",
        "Cache paket uv. Setara dengan `uv cache clean`.",
    ),
    _DevCache(
        "prisma",
        "Cache engine Prisma",
        "~/.cache/prisma",
        "Engine Prisma hasil unduhan. Diunduh ulang saat `prisma generate`.",
    ),
    _DevCache(
        "prisma-nodejs",
        "Cache Prisma (Node.js)",
        "~/.cache/prisma-nodejs",
        "Berkas sementara Prisma untuk Node.js.",
    ),
    _DevCache(
        "checkpoint-nodejs",
        "Cache tooling Node.js",
        "~/.cache/checkpoint-nodejs",
        "Berkas telemetri tooling Node.js (mis. ekstensi VS Code).",
    ),
    _DevCache(
        "playwright",
        "Browser Playwright",
        "~/.cache/ms-playwright",
        "Browser yang diunduh Playwright. Menghapusnya berarti harus menjalankan "
        "`npx playwright install` lagi sebelum test berikutnya.",
        risk=Risk.CAUTION,
        enabled_default=False,
    ),
    _DevCache(
        "puppeteer",
        "Browser Puppeteer",
        "~/.cache/puppeteer",
        "Chrome unduhan Puppeteer. Harus diunduh ulang sebelum dipakai lagi.",
        risk=Risk.CAUTION,
        enabled_default=False,
    ),
)


class DevCacheCleaner(Cleaner):
    id = "dev"
    title = "Cache developer"
    description = "Cache paket dan tooling pengembangan."
    category = "Cache developer"
    icon = "applications-development-symbolic"

    def scan(self) -> list[CleanItem]:
        items: list[CleanItem] = []
        for cache in DEV_CACHES:
            item = self.contents_item(
                f"dev-{cache.item_id}",
                cache.title,
                cache.description,
                [Path(os.path.expanduser(cache.path))],
                risk=cache.risk,
                enabled_default=cache.enabled_default,
            )
            if item.available:
                items.append(item)

        if not items:
            items.append(
                self.unavailable(
                    "dev-cache",
                    "Cache developer",
                    "Cache npm, pip, uv, Prisma, Playwright, dan Puppeteer.",
                    "Tidak ada cache developer yang ditemukan.",
                )
            )
        return items
