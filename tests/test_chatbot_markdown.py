from backend.domains.chatbot.application.answer_formatting import (
    format_user_facing_answer,
)


def test_format_user_facing_answer_restores_large_escaped_inline_table() -> None:
    answer = (
        "Bistelligence Inc. (NASDAQ: BSTL)의 현금흐름 추이는 다음과 같습니다.\n"
        r"\| 항목 | | 2014-12-31 | 2015-12-31 | 2016-12-31 | 2017-12-31 |"
        r" |---|---:|---:|---:|---:| | 영업활동 현금흐름 | 558 | 646 | 750 | 861 |"
    )

    formatted = format_user_facing_answer(answer)

    assert formatted == "\n".join(
        [
            "Bistelligence Inc. (NASDAQ: BSTL)의 현금흐름 추이는 다음과 같습니다.",
            "| 항목 | 2014-12-31 | 2015-12-31 | 2016-12-31 | 2017-12-31 |",
            "| --- | ---: | ---: | ---: | ---: |",
            "| 영업활동 현금흐름 | 558 | 646 | 750 | 861 |",
        ]
    )
