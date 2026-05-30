def test_main_module_exposes_app():
    import i2g_admin.__main__ as main
    from i2g_admin.app import app

    assert main.app is app
