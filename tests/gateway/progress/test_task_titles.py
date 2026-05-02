from gateway.progress.task_titles import summarize_task_intent


def test_weather_retry_question_becomes_intent_summary_not_raw_text():
    title = summarize_task_intent("再试一次。今晚下雨吗？")

    assert title != "再试一次。今晚下雨吗？"
    assert "今晚" in title
    assert "降雨" in title or "下雨" in title
    assert "再试一次" not in title


def test_multilingual_summary_preserves_constraints_without_too_short_cap():
    message = (
        "事务摘要的文字长度不要限制过短，尤其是多语言场景中。"
        "核心目标是把事情说清楚，语义密度尽可能大，信息损失小，信息熵增小。"
    )

    title = summarize_task_intent(message)

    assert len(title) > 40
    assert "多语言" in title
    assert "语义密度" in title
    assert "信息损失" in title
    assert "熵增" in title


def test_optimization_request_is_rephrased_as_task_intent():
    title = summarize_task_intent(
        "事务信息显示的效果，还有一些优化点：1、“任务”字段中内容不是用户的原文，应该是用户意图的摘要。"
    )

    assert title.startswith("优化事务")
    assert "任务" in title
    assert "用户意图摘要" in title
    assert "1、" not in title


def test_english_review_request_is_preserved_without_semantic_loss():
    title = summarize_task_intent("Please review PR #12 for auth regressions without changing code")

    assert "Review PR #12" in title or "review PR #12" in title
    assert "auth regressions" in title
    assert "without changing code" in title


def test_title_redacts_secrets_and_preserves_safe_context():
    title = summarize_task_intent("帮我检查 https://api.example.test/path?token=super-secret-value&ok=1 的问题")

    assert "super-secret-value" not in title
    assert "[REDACTED]" in title
    assert "api.example.test" in title


def test_weather_intent_preserves_explicit_location_and_avoids_unrequested_advice():
    title = summarize_task_intent("上海明天会下雨吗？")

    assert "上海" in title
    assert "明天" in title
    assert "降雨" in title or "下雨" in title
    assert "出行建议" not in title


def test_english_weather_intent_preserves_location_and_language():
    title = summarize_task_intent("Does it rain in Paris tomorrow?")

    assert "Paris" in title
    assert "tomorrow" in title
    assert "rain" in title.lower()
    assert "出行建议" not in title


def test_noise_stripping_does_not_corrupt_chinese_words_starting_with_qing():
    title = summarize_task_intent("请假流程怎么写？")

    assert "请假流程" in title
    assert title != "假流程怎么写？"


def test_generic_request_is_compressed_without_losing_constraints():
    message = "Please fix the login race condition in gateway/run.py and add tests for Telegram and Feishu progress updates, but do not touch billing code."

    title = summarize_task_intent(message)

    assert title != message
    assert "login race condition" in title
    assert "gateway/run.py" in title
    assert "Telegram" in title
    assert "Feishu" in title
    assert "do not touch billing code" in title


def test_english_weather_detection_does_not_match_rain_inside_other_words():
    train_title = summarize_task_intent("Please train the model tomorrow on the new dataset")
    brainstorm_title = summarize_task_intent("Brainstorm tomorrow's launch plan")

    assert "Check rain" not in train_title
    assert "Check rain" not in brainstorm_title
    assert "train the model" in train_title
    assert "Brainstorm" in brainstorm_title


def test_chinese_weather_detection_does_not_match_non_weather_yu_words():
    title = summarize_task_intent("请介绍雨果的作品")

    assert "雨果" in title
    assert "降雨" not in title


def test_chinese_weather_location_after_time_is_preserved():
    title = summarize_task_intent("明天上海会下雨吗？")

    assert "明天" in title
    assert "上海" in title
    assert "降雨" in title or "下雨" in title


def test_english_weather_rewrite_does_not_treat_train_as_rain_after_weather_match():
    title = summarize_task_intent("What is the weather for my train in Paris tomorrow?")

    assert "Check weather" in title
    assert "Check rain" not in title
    assert "Paris" in title
    assert "tomorrow" in title


def test_generic_english_request_without_noise_is_not_raw_text():
    message = "Fix the login race condition in gateway/run.py and add tests for Telegram and Feishu progress updates, but do not touch billing code."

    title = summarize_task_intent(message)

    assert title != message
    assert "login race condition" in title
    assert "gateway/run.py" in title
    assert "Telegram" in title
    assert "Feishu" in title
    assert "do not touch billing code" in title


def test_generic_chinese_request_without_noise_is_not_raw_text():
    message = "请检查数据库连接超时问题，不要修改账单代码"

    title = summarize_task_intent(message)

    assert title != message
    assert "检查" in title
    assert "数据库连接超时" in title
    assert "不要修改账单代码" in title


def test_ok_noise_stripping_does_not_corrupt_okta_or_okr_names():
    okta_title = summarize_task_intent("Okta SSO login fails, investigate without changing billing code")
    okr_title = summarize_task_intent("OKR progress summary for Q2")

    assert "Okta SSO" in okta_title
    assert okta_title != "Handle request: ta SSO login fails, investigate without changing billing code"
    assert okta_title.startswith("Handle request: Okta SSO")
    assert "OKR progress" in okr_title
    assert okr_title != "Handle request: R progress summary for Q2"
    assert okr_title.startswith("Handle request: OKR progress")
