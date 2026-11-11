from __future__ import annotations

from npyquick.main import app_icon


def test_app_icon_loads_every_size():
    icon = app_icon()
    assert not icon.isNull()
    sizes = {size.width() for size in icon.availableSizes()}
    # 16 px is the title bar, 256 px the largest Windows asks for.
    assert {16, 24, 32, 48, 256} <= sizes
