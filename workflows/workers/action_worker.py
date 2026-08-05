"""Action worker — thực thi tool đã bind tại plan stage hoặc LLM chọn tool."""

from __future__ import annotations

import logging

from core.mcp.attachments import ensure_file_path
from core.mcp.hub import format_tools_for_llm, get_tool_hub
from core.mcp.models import ToolCallResult
from core.mcp.ocr_routing import (
    build_ocr_fallback_chain,
    extract_ocr_arguments,
    is_ocr_tool_id,
    ocr_result_has_text,
    ocr_routing_hint_for_llm,
    should_escalate_ocr,
)
from core.planning.media_tasks import plan_media_action_async, resolve_attachment_tool_args
from core.registry.agents import load_registry
from workflows.llm_service import complete_worker_task
from workflows.state import AgentId, SubTask, WorkerResult

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 4

_TOOL_SELECT_SYSTEM = """Bạn là action agent — chọn đúng MCP tool.

Trả JSON:
{{"calls": [{{"tool_id": "server/tool", "arguments": {{}}}}], "done": false, "answer": ""}}

Nếu không cần tool: {{"done": true, "answer": "..."}}

Chỉ dùng tool_id trong danh sách. Server đã có file đính kèm — không cần truyền image_base64.

{ocr_hint}
"""


def _allowed_servers() -> set[str]:
    agent = load_registry().get(AgentId.ACTION_WORKER)
    if not agent or not agent.tools:
        return {"builtin-translate", "builtin-ocr", "builtin-image"}
    return set(agent.tools)


async def run_action_worker(
    task: SubTask,
    *,
    chat_history: list[dict] | None = None,
    attachments: list[dict] | None = None,
) -> WorkerResult:
    hub = get_tool_hub()
    servers = _allowed_servers()
    tools = hub.list_tools(server_filter=servers)
    available_ids = {t.id for t in tools}
    tools_called: list[str] = []
    tool_outputs: list[str] = []
    ocr_handled = False

    if task.tool_id:
        calls = [{"tool_id": task.tool_id, "arguments": dict(task.tool_arguments)}]
        logger.info("Execute planned tool kind=%s tool=%s", task.task_kind, task.tool_id)
    else:
        plan = await _plan_tool_calls(
            task.description, tools, chat_history=chat_history, attachments=attachments
        )
        if plan.get("done") and plan.get("answer"):
            return WorkerResult(
                task_id=task.id,
                agent=AgentId.ACTION_WORKER,
                summary=plan["answer"],
                success=True,
                tools_called=tools_called,
            )
        calls = plan.get("calls", [])

    for call in calls[:_MAX_TOOL_ROUNDS]:
        tool_id = str(call.get("tool_id", "")).strip()
        arguments = dict(call.get("arguments") or {})
        if not tool_id:
            continue

        if is_ocr_tool_id(tool_id):
            if ocr_handled:
                continue
            ocr_handled = True

        for executed_id, result in await _execute_with_escalation(
            hub,
            tool_id,
            arguments,
            task.description,
            available_ids,
            attachments=attachments,
            task_kind=task.task_kind,
            high_accuracy=task.high_accuracy,
        ):
            tools_called.append(executed_id)
            if result.success:
                tool_outputs.append(f"### {executed_id}\n{result.content}")
            else:
                tool_outputs.append(f"### {executed_id} (lỗi)\n{result.error or result.content}")

    if not tool_outputs:
        summary = await complete_worker_task(
            AgentId.ACTION_WORKER,
            task.description,
            extra_context=_tools_context(tools),
            chat_history=chat_history,
        )
        if not summary:
            summary = (
                f"Không thực thi được tool MCP cho: {task.description[:200]}\n\n"
                "Bật server trong `config/mcp_servers.yaml` (enabled: true) "
                "hoặc cấu hình LLM để agent chọn tool."
            )
        return WorkerResult(
            task_id=task.id,
            agent=AgentId.ACTION_WORKER,
            summary=summary,
            success=True,
            tools_called=tools_called,
        )

    synthesis = _summary_from_tool_outputs(tool_outputs)
    if not synthesis:
        synthesis = await complete_worker_task(
            AgentId.ACTION_WORKER,
            task.description,
            extra_context="Kết quả tool:\n" + "\n\n".join(tool_outputs),
            chat_history=chat_history,
        )
    summary = synthesis or "\n\n".join(tool_outputs)

    return WorkerResult(
        task_id=task.id,
        agent=AgentId.ACTION_WORKER,
        summary=summary,
        success=True,
        tools_called=tools_called,
    )


async def _execute_with_escalation(
    hub,
    tool_id: str,
    arguments: dict,
    task: str,
    available_ids: set[str],
    *,
    attachments: list[dict] | None = None,
    task_kind: str = "",
    high_accuracy: bool = False,
) -> list[tuple[str, ToolCallResult]]:
    """OCR: fallback chain từ config; tool khác gọi trực tiếp."""
    if not is_ocr_tool_id(tool_id):
        result = await hub.call_tool(tool_id, arguments)
        return [(tool_id, result)]

    ocr_args = {**(arguments or {})}
    ocr_args.update(
        {k: v for k, v in resolve_attachment_tool_args(attachments, message=task).items() if v}
    )
    logger.info(
        "OCR args file=%s has_b64=%s kind=%s",
        bool(ocr_args.get("file_path")),
        bool(ocr_args.get("image_base64")),
        task_kind or "ocr",
    )

    chain = build_ocr_fallback_chain(
        available_tool_ids=available_ids,
        high_accuracy=high_accuracy,
    )
    if tool_id in chain:
        chain = [tool_id] + [t for t in chain if t != tool_id]
    elif tool_id:
        chain = [tool_id] + chain

    executed: list[tuple[str, ToolCallResult]] = []
    for candidate_id in chain:
        call_args = ocr_args if candidate_id.startswith("builtin-") else ensure_file_path(ocr_args)

        logger.info("OCR try tool=%s", candidate_id)
        result = await hub.call_tool(candidate_id, call_args)
        executed.append((candidate_id, result))

        if ocr_result_has_text(result.content, success=result.success):
            logger.info("OCR success tool=%s", candidate_id)
            break
        if not should_escalate_ocr(task, result.content, success=result.success):
            break

    return executed


async def _plan_tool_calls(
    task: str,
    tools,
    *,
    chat_history: list[dict] | None,
    attachments: list[dict] | None = None,
) -> dict:
    from core.llm.client import get_llm_client

    client = get_llm_client()
    available_ids = {t.id for t in tools}

    media = await plan_media_action_async(
        task,
        attachments,
        available_tool_ids=available_ids,
        chat_history=chat_history,
    )
    if media and media.tool_arguments:
        return {
            "done": False,
            "calls": [{"tool_id": media.tool_id, "arguments": media.tool_arguments}],
        }

    if not client.enabled or not tools:
        return {"done": False, "calls": _keyword_fallback_calls(task, available_ids, attachments)}

    catalog = format_tools_for_llm(tools)
    system = _TOOL_SELECT_SYSTEM.format(ocr_hint=ocr_routing_hint_for_llm())
    attach_note = ""
    if attachments:
        attach_note = (
            f"\n\nUser đính kèm {len(attachments)} file — server đã lưu file_path, "
            "không cần image_base64."
        )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Task: {task}{attach_note}\n\nTools:\n{catalog}"},
    ]
    if chat_history:
        for m in chat_history[-4:]:
            if m.get("role") in ("user", "assistant") and m.get("content"):
                messages.insert(-1, {"role": m["role"], "content": m["content"][:1500]})

    data = await client.chat_json("worker", messages, agent_id=AgentId.ACTION_WORKER)
    if not data:
        return {"calls": _keyword_fallback_calls(task, available_ids, attachments), "done": False, "answer": ""}
    if not data.get("calls"):
        data["calls"] = _keyword_fallback_calls(task, available_ids, attachments)
    return data


def _keyword_fallback_calls(
    task: str,
    available_ids: set[str],
    attachments: list[dict] | None = None,
) -> list[dict]:
    from core.planning.media_tasks import plan_media_action

    media = plan_media_action(task, attachments, available_tool_ids=available_ids)
    if media:
        return [{"tool_id": media.tool_id, "arguments": media.tool_arguments}]
    return []


def _tools_context(tools) -> str:
    lines = ["Các MCP tool khả dụng:", ocr_routing_hint_for_llm()]
    for t in tools:
        lines.append(f"- {t.id}: {t.description}")
    return "\n".join(lines)


def _summary_from_tool_outputs(tool_outputs: list[str]) -> str | None:
    """Trả text OCR trực tiếp — tránh LLM bịa hướng dẫn cài Tesseract."""
    import json

    for block in tool_outputs:
        payload = block.split("\n", 1)[-1] if "\n" in block else block
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("text"):
            engine = data.get("engine", "ocr")
            return f"**Nội dung đọc từ ảnh** (_{engine}_):\n\n{data['text']}"
        if isinstance(data, dict) and data.get("error"):
            return f"**Không đọc được ảnh:** {data['error']}"
    return None
