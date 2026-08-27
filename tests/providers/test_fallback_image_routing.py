"""Image-aware model routing in FallbackProvider.

When the primary preset is marked ``supportsImages: false`` and the request
payload contains image blocks, the primary is skipped and the turn goes
straight to the fallback chain (e.g. a multimodal preset). Text-only turns
keep using the primary.
"""

from typing import Any

from nanobot.config.schema import ModelPresetConfig
from nanobot.providers.base import LLMProvider, LLMResponse
from nanobot.providers.fallback_provider import FallbackProvider


class _FakeProvider(LLMProvider):
    def __init__(self, name: str, content: str) -> None:
        super().__init__(provider_name=name)
        self.name = name
        self.content = content
        self.chat_calls: list[dict[str, Any]] = []
        self.chat_stream_calls: list[dict[str, Any]] = []

    def get_default_model(self) -> str:
        return f"{self.name}-model"

    async def chat(self, **kwargs: Any) -> LLMResponse:
        self.chat_calls.append(kwargs)
        return LLMResponse(content=self.content, finish_reason="stop")

    async def chat_stream(self, **kwargs: Any) -> LLMResponse:
        self.chat_stream_calls.append(kwargs)
        return LLMResponse(content=self.content, finish_reason="stop")


def _vision_preset() -> ModelPresetConfig:
    return ModelPresetConfig(
        model="qwen3.8-max",
        provider="dashscope_native",
        max_tokens=4096,
        temperature=0.1,
    )


def _image_messages() -> list[dict[str, Any]]:
    return [{
        "role": "user",
        "content": [
            {"type": "text", "text": "这张图里是什么？"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}},
        ],
    }]


def _text_messages() -> list[dict[str, Any]]:
    return [{"role": "user", "content": "你好"}]


def _make_wrapper(
    primary: _FakeProvider,
    fallback: _FakeProvider,
    *,
    primary_supports_images: bool | None,
) -> FallbackProvider:
    return FallbackProvider(
        primary=primary,
        fallback_presets=[_vision_preset()],
        provider_factory=lambda _preset: fallback,
        primary_supports_images=primary_supports_images,
    )


async def test_image_turn_routes_to_fallback_when_primary_lacks_vision() -> None:
    primary = _FakeProvider("primary", "primary answer")
    fallback = _FakeProvider("vision", "vision answer")
    wrapper = _make_wrapper(primary, fallback, primary_supports_images=False)

    response = await wrapper.chat(messages=_image_messages(), model="deepseek-v4-flash-0731")

    assert response.content == "vision answer"
    assert primary.chat_calls == []
    assert len(fallback.chat_calls) == 1
    assert fallback.chat_calls[0]["model"] == "qwen3.8-max"


async def test_text_turn_still_uses_primary() -> None:
    primary = _FakeProvider("primary", "primary answer")
    fallback = _FakeProvider("vision", "vision answer")
    wrapper = _make_wrapper(primary, fallback, primary_supports_images=False)

    response = await wrapper.chat(messages=_text_messages(), model="deepseek-v4-flash-0731")

    assert response.content == "primary answer"
    assert len(primary.chat_calls) == 1
    assert fallback.chat_calls == []


async def test_routing_inactive_when_capability_unknown() -> None:
    primary = _FakeProvider("primary", "primary answer")
    fallback = _FakeProvider("vision", "vision answer")
    wrapper = _make_wrapper(primary, fallback, primary_supports_images=None)

    response = await wrapper.chat(messages=_image_messages(), model="deepseek-v4-flash-0731")

    assert response.content == "primary answer"
    assert len(primary.chat_calls) == 1
    assert fallback.chat_calls == []


async def test_streaming_image_turn_routes_to_fallback() -> None:
    primary = _FakeProvider("primary", "primary answer")
    fallback = _FakeProvider("vision", "vision answer")
    wrapper = _make_wrapper(primary, fallback, primary_supports_images=False)

    response = await wrapper.chat_stream(messages=_image_messages())

    assert response.content == "vision answer"
    assert primary.chat_stream_calls == []
    assert len(fallback.chat_stream_calls) == 1
    assert fallback.chat_stream_calls[0]["model"] == "qwen3.8-max"


def test_preset_config_accepts_camel_case_supports_images() -> None:
    preset = ModelPresetConfig.model_validate({
        "model": "deepseek-v4-flash-0731",
        "provider": "dashscope",
        "supportsImages": False,
    })
    assert preset.supports_images is False

    unknown = ModelPresetConfig.model_validate({"model": "m", "provider": "auto"})
    assert unknown.supports_images is None
