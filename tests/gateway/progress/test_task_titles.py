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


def test_generic_task_optimization_point_is_not_exact_raw_text():
    message = "这个任务还有优化点"

    title = summarize_task_intent(message)

    assert title == "梳理任务优化点"
    assert title != message


def test_generic_task_optimization_point_preserves_specific_content():
    message = "这个任务的优化点是减少日志噪音"

    title = summarize_task_intent(message)

    assert title == "梳理任务优化点：减少日志噪音"
    assert title != message
    assert "减少日志噪音" in title


def test_english_review_request_is_preserved_without_semantic_loss():
    title = summarize_task_intent("Please review PR #12 for auth regressions without changing code")

    assert "PR #12" in title
    assert "auth regressions" in title
    assert "without changing code" in title
    assert not title.startswith("Handle request:")


def test_title_redacts_secrets_and_preserves_safe_context():
    title = summarize_task_intent("帮我检查 https://api.example.test/path?token=super-secret-value&ok=1 的问题")

    assert "super-secret-value" not in title
    assert "[REDACTED]" in title
    assert "api.example.test" in title


def test_command_or_authorization_shaped_request_becomes_safe_summary():
    messages = [
        'Please review curl -H "Authorization: Bearer *** https://example.test/path?token=x',
        '-H "X-Api-Key: x" https://example.test/path?token=x',
        '--header "Cookie: session=abc123" https://example.test/path?token=x',
    ]

    for message in messages:
        title = summarize_task_intent(message)

        assert title == "Handle command or authorization-related request safely"
        assert "curl" not in title
        assert "Authorization" not in title
        assert "X-Api-Key" not in title
        assert "Cookie" not in title
        assert "Bearer" not in title
        assert "example.test" not in title
        assert "token" not in title
        assert "super-secret" not in title


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


def test_chinese_weather_detection_does_not_match_weather_card_product_terms():
    title = summarize_task_intent("优化事务卡显示，不要修改天气卡")

    assert title == "改进事务卡显示；约束：不要修改天气卡"
    assert "天气卡" in title
    assert "查询" not in title
    assert "指定时段" not in title


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
    assert title != f"处理请求：{message}"
    assert "数据库连接超时" in title
    assert "不要修改账单代码" in title


def test_generic_chinese_question_does_not_use_raw_with_prefix_fallback():
    message = "需要更新代码吗？还是怎么着？"

    title = summarize_task_intent(message)

    assert title == "评估是否需要更新代码并给出处理建议"
    assert title != message
    assert title != f"处理请求：{message}"
    assert "还是怎么着" not in title


def test_generic_chinese_question_preserves_negative_constraint():
    message = "需要更新代码吗？不要修改账单代码"

    title = summarize_task_intent(message)

    assert title == "评估是否需要更新代码并给出处理建议；约束：不要修改账单代码"
    assert title != message
    assert title != f"处理请求：{message}"
    assert "不要修改账单代码" in title


def test_generic_english_question_preserves_negative_constraint():
    message = "Do we need to update code? Do not touch billing code"

    title = summarize_task_intent(message)

    assert title == "Assess whether code updates are needed; constraint: Do not touch billing code"
    assert title != message
    assert title != "Summarize user intent"
    assert "Do not touch billing code" in title


def test_generic_english_question_preserves_inline_without_constraint():
    message = "Do we need to update code without changing billing code"

    title = summarize_task_intent(message)

    assert title == "Assess whether code updates are needed; constraint: without changing billing code"
    assert title != message
    assert title != "Summarize user intent"
    assert "without changing billing code" in title


def test_generic_english_modal_request_preserves_action_object_and_constraint():
    message = "Can you fix the login bug without changing billing code?"

    title = summarize_task_intent(message)

    assert title == "Resolve the login bug; constraint: without changing billing code"
    assert title != message
    assert "login bug" in title
    assert "without changing billing code" in title


def test_generic_english_modal_multi_action_request_rewrites_modal_wrapper():
    message = "Could you check the database timeout issue and add tests?"

    title = summarize_task_intent(message)

    assert title == "Inspect the database timeout issue; add tests"
    assert title != message
    assert "Could you" not in title
    assert "database timeout issue" in title
    assert "add tests" in title


def test_non_latin_multilingual_request_never_returns_raw_text():
    message = "Исправь ошибку без изменения биллинга"

    title = summarize_task_intent(message)

    assert title == "Summarize multilingual user intent"
    assert title != message


def test_simple_english_action_request_is_not_exact_raw_text():
    message = "Fix bug"

    title = summarize_task_intent(message)

    assert title == "Resolve bug"
    assert title != message


def test_simple_chinese_action_request_is_not_exact_raw_text():
    message = "检查数据库连接超时问题"

    title = summarize_task_intent(message)

    assert title == "排查数据库连接超时问题"
    assert title != message


def test_model_configuration_question_becomes_intent_summary():
    message = "现在你在使用什么模型？思考强度是多少？"

    title = summarize_task_intent(message)

    assert title == "说明当前模型与思考强度配置"
    assert title != message
    assert title != f"处理请求：{message}"
    assert "现在你在使用" not in title


def test_bug_report_about_raw_task_field_becomes_fix_intent_summary():
    message = (
        "发现一个问题，你在事务信息卡中的“任务”字段还是显示了我发出的原文。"
        "并没有完全遵守我之前的要求：“任务”字段中内容不是用户的原文，应该是用户意图的摘要。"
        "事务摘要的文字长度不要限制过短，尤其是多语言场景中。"
        "核心目标是把事情说清楚，语义密度尽可能大，信息损失小，信息熵增小。"
    )

    title = summarize_task_intent(message)

    assert title.startswith("修复事务卡任务字段仍显示用户原文的问题")
    assert "多语言" in title
    assert "高语义密度" in title
    assert "低信息损失" in title
    assert "低信息熵增" in title
    assert title != message
    assert not title.startswith("处理请求：")


def test_current_time_question_becomes_query_current_time():
    title = summarize_task_intent("现在几点了？")

    assert title == "查询当前时间"
    assert title != "现在几点了？"


def test_current_date_question_becomes_query_current_date():
    title = summarize_task_intent("今天几号？")

    assert title == "查询当前日期"
    assert title != "今天几号？"


def test_meeting_time_question_is_not_collapsed_to_query_current_time():
    # "几点" appears inside a scheduling question, not a time-of-day utility query.
    # The datetime rewrite must not swallow the meeting/scheduling intent.
    title = summarize_task_intent("今天几点开会？")

    assert title != "查询当前时间"
    assert "开会" in title


def test_date_parsing_bugfix_is_not_collapsed_to_query_current_date():
    # "当前日期" appears inside a bugfix request, not a date utility query.
    # The datetime rewrite must not swallow the fix/parse intent.
    title = summarize_task_intent("修复当前日期解析问题")

    assert title != "查询当前日期"
    assert "当前日期解析问题" in title


def test_ok_noise_stripping_does_not_corrupt_okta_or_okr_names():
    okta_title = summarize_task_intent("Okta SSO login fails, investigate without changing billing code")
    okr_title = summarize_task_intent("OKR progress summary for Q2")

    assert "Okta SSO" in okta_title
    assert okta_title != "Handle request: ta SSO login fails, investigate without changing billing code"
    assert not okta_title.startswith("Handle request:")
    assert "OKR progress" in okr_title
    assert okr_title != "Handle request: R progress summary for Q2"
    assert not okr_title.startswith("Handle request:")


def test_task_workbench_title_issue_becomes_concise_task_title_not_raw_details():
    message = (
        "OK。现在我们聚焦 sachima 项目，我发现主线外的一个小问题：\n"
        "飞书任务工作台富交互卡中的“任务”内容描述不太稳定，有时是固定回复“提炼并处理用户意图”没走摘要，"
        "有时又太过具体（一大段话）。\n"
        "我想要的是根据对话上下文分析用户意图并简练摘要成一句话标题，无需细节。"
    )

    title = summarize_task_intent(message)

    assert title == "优化飞书任务工作台任务标题摘要生成"
    assert title != message
    assert "提炼并处理用户意图" not in title
    assert "一大段" not in title
    assert len(title) <= 32


def test_approval_turn_uses_recent_substantive_context_instead_of_generic_fallback():
    context = [
        {"role": "user", "content": "OK，先讨论清楚。"},
        {
            "role": "user",
            "content": (
                "飞书任务工作台富交互卡中的“任务”内容描述不太稳定。"
                "需要根据对话上下文把用户意图简练摘要成一句话标题。"
            ),
        },
        {
            "role": "assistant",
            "content": "方案：实现任务标题摘要生成、语言判定和安全兜底。",
        },
    ]

    for acknowledgement in ("接下来走正规开发流程。批准开始实施。", "OK"):
        title = summarize_task_intent(acknowledgement, context_messages=context)

        assert title == "优化飞书任务工作台任务标题摘要生成"
        assert title != "提炼并处理用户意图"
        assert title != acknowledgement


def test_acknowledgement_without_context_uses_safe_specific_fallback_not_summary_placeholder():
    title = summarize_task_intent("批准开始实施")

    assert title == "推进已确认任务"
    assert title != "提炼并处理用户意图"
