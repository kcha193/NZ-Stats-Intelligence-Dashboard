from nzstats.slug import slugify


def test_slugify() -> None:
    assert slugify("China, People's Republic of") == "china-peoples-republic-of"
    assert slugify("Tatauranga umanga Māori – x") == "tatauranga-umanga-maori-x"
    assert slugify("  Not Stated ") == "not-stated"
