import ast
from datetime import datetime
import json
import os
import re
import uuid
from typing import Any

from dotenv import load_dotenv

from config import DEBUG_SAVE_AI_RESPONSE, TEMP_DIR

load_dotenv()

ERROR_MESSAGES = {
    "groq_auth": "❌ Groq API key is invalid or missing. Check GROQ_API_KEY in your .env file.",
    "groq_ratelimit": "⏳ Groq rate limit hit. Wait a moment and try again, or switch to OpenRouter.",
    "groq_model_not_found": "❌ Groq model not found. Check the model name — try 'llama-3.1-8b-instant'.",
    "groq_timeout": "⏱️ Groq request timed out. Try again or switch provider.",
    "groq_network": "🌐 Cannot reach Groq. Check your internet connection.",
    "gemini_auth": "❌ Google API key is invalid or missing.",
    "gemini_ratelimit": "⏳ Gemini rate limit hit. Wait a moment and try again.",
    "gemini_model_not_found": "❌ Gemini model not found. Check the model name — try 'gemini-2.0-flash'.",
    "gemini_server": "🔧 Gemini server error. Try again in a moment.",
    "gemini_network": "🌐 Cannot reach Gemini. Check your internet connection.",
    "gemini_timeout": "⏱️ Gemini request timed out. Try again or switch provider.",
    "openrouter_auth": "❌ OpenRouter API key is invalid or missing. Check OPENROUTER_API_KEY in your .env file.",
    "openrouter_ratelimit": "⏳ OpenRouter rate limit hit. Wait a moment and try again.",
    "openrouter_credits": "💳 OpenRouter account has no credits. Add credits at openrouter.ai or use a free model.",
    "openrouter_model_not_found": "❌ OpenRouter model not found. Check the model name at openrouter.ai/models.",
    "openrouter_server": "🔧 OpenRouter server error. Try again in a moment.",
    "openrouter_network": "🌐 Cannot reach OpenRouter. Check your internet connection.",
    "openrouter_timeout": "⏱️ OpenRouter request timed out. Try again or switch provider.",
    "ollama_not_running": "❌ Ollama is not running. Start it with: ollama serve",
    "ollama_model_not_found": "❌ Ollama model not found. Pull it first with: ollama pull <model-name>",
    "ollama_server": "🔧 Ollama server error. Restart Ollama and try again.",
    "ollama_timeout": "⏱️ Ollama timed out. The model may be too large or your machine too slow.",
    "parse_failed": "❌ AI returned an invalid response format. Try again, switch model, or switch provider.",
    "no_valid_clips": "❌ AI returned clips, but none had usable start/end timestamps. Try a different model or provider.",
    "unknown_provider": "❌ Unknown AI provider selected. Choose Groq, Gemini, OpenRouter, or Ollama.",
}


class HighlightDetector:
    def __init__(self, provider: str, model: str, api_keys: dict):
        self.provider = provider
        self.provider_key = provider.strip().lower()
        self.model = model
        self.api_keys = {
            "groq": api_keys.get("groq") or os.environ.get("GROQ_API_KEY", ""),
            "gemini": api_keys.get("gemini") or os.environ.get("GOOGLE_API_KEY", ""),
            "openrouter": api_keys.get("openrouter")
            or os.environ.get("OPENROUTER_API_KEY", ""),
        }

    def _save_debug_response(self, raw_response):
        if not DEBUG_SAVE_AI_RESPONSE:
            return
        try:
            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            suffix = uuid.uuid4().hex[:8]
            path = (
                TEMP_DIR / f"ai_response_{self.provider_key}_{timestamp}_{suffix}.txt"
            )
            if isinstance(raw_response, str):
                content = raw_response
            else:
                content = json.dumps(raw_response, ensure_ascii=False, indent=2)
            path.write_text(content, encoding="utf-8")
        except Exception:
            pass

    def find_highlights(
        self,
        transcript_words,
        num_clips,
        min_dur,
        max_dur,
        user_guidance="",
        include_hook=True,
    ):
        transcript = self._format_transcript(transcript_words)
        messages = self._build_messages(
            transcript, num_clips, min_dur, max_dur, user_guidance, include_hook
        )
        try:
            clips = None
            if self.provider_key == "groq":
                clips = self._call_groq(messages)
            elif self.provider_key == "gemini":
                clips = self._call_gemini(messages)
            elif self.provider_key == "openrouter":
                clips = self._call_openrouter(messages)
            elif self.provider_key == "ollama":
                clips = self._call_ollama(messages)
            else:
                raise RuntimeError("unknown_provider")
            return self._normalize_clips(clips)
        except RuntimeError as exc:
            raise RuntimeError(self._friendly_error(str(exc))) from None
        except Exception as exc:
            raise RuntimeError(self._friendly_error(str(exc))) from None

    def _format_transcript(self, transcript_words):
        lines = []
        for i, word in enumerate(transcript_words):
            if i % 10 == 0:
                start = int(word["start"])
                mins, secs = divmod(start, 60)
                lines.append(f"[{mins:02d}:{secs:02d}]")
            lines.append(word["word"])
        return " ".join(lines)

    def _build_messages(
        self, transcript, num_clips, min_dur, max_dur, user_guidance, include_hook
    ):
        guidance_block = (
            f"Additional clip guidance from the user: {user_guidance.strip()}\n\n"
            if user_guidance.strip()
            else ""
        )
        hook_instruction = (
            "HOOK RULES:\n"
            '- Include a "hook" field for each clip.\n'
            "- The hook MUST be directly derived from what is actually said or "
            "happens in that specific clip segment. Read the transcript of that "
            "segment carefully and write a hook that reflects its actual content, "
            "topic, or punchline.\n"
            "- Never write a generic hook like 'You Won't Believe This' or "
            "'This Is Insane' unless the clip literally contains a shocking reveal.\n"
            "- The hook should tease the specific idea, opinion, story, or moment "
            "in that clip — a viewer should be able to guess the topic from the "
            "hook alone.\n"
            "- Format: 4-8 words (Max 36 characeters), punchy, present tense, NO emojis, plain text only.\n"
            "- Examples of GOOD hooks: 'He quit his job on day one', "
            "'This mistake cost me 50k', 'Nobody talks about this tax trick'\n"
            "- Examples of BAD hooks: 'You Won't Believe This', "
            "'This Is Wild', 'Watch Till The End'\n\n"
            if include_hook
            else ""
        )
        example = (
            '[{"start_time": 12.4, "end_time": 67.8, "reason": "...", '
            '"virality_score": 8.5, "hook": "He quit his job on day one"}]'
            if include_hook
            else '[{"start_time": 12.4, "end_time": 67.8, "reason": "...", '
            '"virality_score": 8.5}]'
        )
        return [
            {
                "role": "system",
                "content": (
                    "You are an expert short-form video editor who specializes "
                    "in creating viral clips. Your job is to find self-contained, "
                    "emotionally complete moments from transcripts.\n\n"
                    "OUTPUT FORMAT RULES — CRITICAL:\n"
                    "- Your ENTIRE response must be a single valid JSON array.\n"
                    "- Start your response with [ and end with ].\n"
                    "- No text before the [. No text after the ].\n"
                    "- No markdown. No backticks. No code fences. No explanation.\n"
                    "- No preamble like 'Here are the clips:' or 'Sure! Here is...'.\n"
                    "- If you add ANY text outside the JSON array, the entire "
                    "response will be rejected and the user's video will fail.\n"
                    "- ONLY output the raw JSON array. Nothing else."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Analyze this transcript and find the {num_clips} most "
                    f"engaging segments for viral short-form clips. Each clip "
                    f"must be between {min_dur} and {max_dur} seconds long.\n\n"
                    "STRICT RULES FOR CLIP SELECTION:\n"
                    "1. COMPLETE THOUGHTS ONLY — Every clip must start at the "
                    "beginning of a sentence or idea, and end only after the "
                    "sentence, story, or point is fully resolved. Never cut "
                    "mid-sentence, mid-story, or before the punchline lands.\n"
                    "2. START WITH CONTEXT — The clip must start slightly before "
                    "the key moment so the viewer has enough context. Never drop "
                    "the viewer into the middle of a thought.\n"
                    "3. END WITH RESOLUTION — The clip must end after a natural "
                    "pause, conclusion, laugh, reaction, or clear stopping point. "
                    "If a story or argument is building, include its payoff.\n"
                    "4. PREFER LONGER OVER INCOMPLETE — If a complete thought "
                    "requires more time, use more of the allowed duration. "
                    f"A {max_dur}s complete clip is always better than a "
                    f"{min_dur}s incomplete one.\n"
                    "5. NO OVERLAPPING CLIPS — Clips must not overlap in time.\n"
                    "6. LOOK FOR: strong opinions, surprising reveals, emotional "
                    "moments, funny reactions, clear advice or tips, storytelling "
                    "with a beginning-middle-end, controversial takes.\n"
                    "7. AVOID: mid-sentence starts, abrupt endings, clips that "
                    "reference something not shown, filler words at the start "
                    "like 'um', 'so', 'and', 'but' as the very first word.\n\n"
                    f"{hook_instruction}"
                    f"{guidance_block}"
                    "REMEMBER: Respond with ONLY the JSON array. "
                    "TIMESTAMP RULES — CRITICAL:\n"
                    "- start_time and end_time must be in SECONDS as a decimal number.\n"
                    "- The transcript uses [MM:SS] markers. Convert them to seconds.\n"
                    "- Examples of correct conversion:\n"
                    "  [00:30] = 30.0 seconds\n"
                    "  [01:00] = 60.0 seconds\n"
                    "  [02:06] = 126.0 seconds\n"
                    "  [05:39] = 339.0 seconds\n"
                    "  [10:00] = 600.0 seconds\n"
                    "- NEVER write 206 for 2:06. ALWAYS convert: minutes × 60 + seconds.\n"
                    "- Double-check every timestamp before returning.\n\n"
                    "Start with [ and end with ]. No other text.\n\n"
                    f"Example of EXACT required format:\n{example}\n\n"
                    f"Transcript:\n{transcript}"
                ),
            },
        ]

    def _call_groq(self, messages):
        try:
            from groq import Groq, AuthenticationError, RateLimitError, APIError

            if not self.api_keys.get("groq", "").strip():
                raise RuntimeError("groq_auth")
            client = Groq(api_key=self.api_keys.get("groq", ""))
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                timeout=60,
            )
            content = response.choices[0].message.content
            self._save_debug_response(content)
            return self._parse(content)
        except AuthenticationError:
            raise RuntimeError("groq_auth")
        except RateLimitError:
            raise RuntimeError("groq_ratelimit")
        except APIError as e:
            msg = str(e).lower()
            if "model" in msg and ("not found" in msg or "does not exist" in msg):
                raise RuntimeError("groq_model_not_found")
            raise RuntimeError(f"groq_api:{e}")
        except Exception as e:
            msg = str(e).lower()
            if "api key" in msg or "401" in msg:
                raise RuntimeError("groq_auth")
            if "429" in msg or "rate" in msg:
                raise RuntimeError("groq_ratelimit")
            if "timeout" in msg:
                raise RuntimeError("groq_timeout")
            if "connect" in msg or "network" in msg:
                raise RuntimeError("groq_network")
            raise

    def _call_gemini(self, messages):
        import requests

        try:
            api_key = self.api_keys.get("gemini", "").strip()
            if not api_key:
                raise RuntimeError("gemini_auth")

            system_parts = []
            contents = []
            for message in messages:
                role = str(message.get("role", "")).strip().lower()
                content = str(message.get("content", "")).strip()
                if not content:
                    continue
                if role == "system":
                    system_parts.append({"text": content})
                    continue
                contents.append(
                    {
                        "role": "model" if role == "assistant" else "user",
                        "parts": [{"text": content}],
                    }
                )

            payload = {
                "contents": contents,
                "generationConfig": {
                    "responseMimeType": "application/json",
                },
            }
            if system_parts:
                payload["systemInstruction"] = {"parts": system_parts}

            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                params={"key": api_key},
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            if response.status_code == 400:
                detail = response.text.lower()
                if "api key" in detail or "authentication" in detail:
                    raise RuntimeError("gemini_auth")
                if "model" in detail and (
                    "not found" in detail or "unsupported" in detail
                ):
                    raise RuntimeError("gemini_model_not_found")
            if response.status_code in (401, 403):
                raise RuntimeError("gemini_auth")
            if response.status_code == 404:
                raise RuntimeError("gemini_model_not_found")
            if response.status_code == 429:
                raise RuntimeError("gemini_ratelimit")
            if response.status_code >= 500:
                raise RuntimeError("gemini_server")
            response.raise_for_status()

            data = response.json()
            if "error" in data:
                err = data["error"]
                status = str(err.get("status", "")).upper()
                err_msg = str(err.get("message", "")).lower()
                if (
                    status in {"UNAUTHENTICATED", "PERMISSION_DENIED"}
                    or "api key" in err_msg
                ):
                    raise RuntimeError("gemini_auth")
                if (
                    status == "RESOURCE_EXHAUSTED"
                    or "rate" in err_msg
                    or "quota" in err_msg
                ):
                    raise RuntimeError("gemini_ratelimit")
                if status == "NOT_FOUND" or (
                    "model" in err_msg and "not found" in err_msg
                ):
                    raise RuntimeError("gemini_model_not_found")
                raise RuntimeError(f"gemini_api:{err.get('message', 'unknown')}")

            candidates = data.get("candidates") or []
            parts = ((candidates[0] if candidates else {}).get("content") or {}).get(
                "parts"
            ) or []
            content = "".join(str(part.get("text", "")) for part in parts).strip()
            if not content:
                raise RuntimeError("parse_failed")
            self._save_debug_response(content)
            return self._parse(content)
        except RuntimeError:
            raise
        except requests.exceptions.ConnectionError:
            raise RuntimeError("gemini_network")
        except requests.exceptions.Timeout:
            raise RuntimeError("gemini_timeout")
        except Exception as e:
            msg = str(e).lower()
            if "api key" in msg or "401" in msg or "403" in msg:
                raise RuntimeError("gemini_auth")
            if "429" in msg or "rate" in msg or "quota" in msg:
                raise RuntimeError("gemini_ratelimit")
            if "model" in msg and "not found" in msg:
                raise RuntimeError("gemini_model_not_found")
            if "timeout" in msg:
                raise RuntimeError("gemini_timeout")
            if "connect" in msg or "network" in msg:
                raise RuntimeError("gemini_network")
            raise RuntimeError(f"gemini_api:{e}")

    def _call_openrouter(self, messages):
        import requests

        try:
            if not self.api_keys.get("openrouter", "").strip():
                raise RuntimeError("openrouter_auth")
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_keys.get('openrouter', '')}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://revoclip.local",
                    "X-Title": "Revoclip",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                },
                timeout=60,
            )
            if response.status_code == 401:
                raise RuntimeError("openrouter_auth")
            if response.status_code == 429:
                raise RuntimeError("openrouter_ratelimit")
            if response.status_code == 402:
                raise RuntimeError("openrouter_credits")
            if response.status_code == 404:
                raise RuntimeError("openrouter_model_not_found")
            if response.status_code >= 500:
                raise RuntimeError("openrouter_server")
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                err = data["error"]
                code = err.get("code", 0)
                err_msg = err.get("message", "").lower()
                if code == 401 or "auth" in err_msg or "key" in err_msg:
                    raise RuntimeError("openrouter_auth")
                if code == 429 or "rate" in err_msg:
                    raise RuntimeError("openrouter_ratelimit")
                if "model" in err_msg and "not found" in err_msg:
                    raise RuntimeError("openrouter_model_not_found")
                if "credit" in err_msg or "balance" in err_msg:
                    raise RuntimeError("openrouter_credits")
                raise RuntimeError(f"openrouter_api:{err.get('message', 'unknown')}")
            content = data["choices"][0]["message"]["content"]
            self._save_debug_response(content)
            return self._parse(content)
        except RuntimeError:
            raise
        except requests.exceptions.ConnectionError:
            raise RuntimeError("openrouter_network")
        except requests.exceptions.Timeout:
            raise RuntimeError("openrouter_timeout")
        except Exception as e:
            raise RuntimeError(f"openrouter_api:{e}")

    def _call_ollama(self, messages):
        import requests

        ollama_url = "http://localhost:11434/api/chat"
        try:
            response = requests.post(
                ollama_url,
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                },
                timeout=300,
            )
            if response.status_code == 404:
                raise RuntimeError("ollama_model_not_found")
            if response.status_code == 500:
                raise RuntimeError("ollama_server")
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
            self._save_debug_response(content)
            return self._parse(content)
        except RuntimeError:
            raise
        except requests.exceptions.ConnectionError:
            raise RuntimeError("ollama_not_running")
        except requests.exceptions.Timeout:
            raise RuntimeError("ollama_timeout")
        except Exception as e:
            raise RuntimeError(f"ollama_api:{e}")

    def _parse(self, raw: str, retries: int = 3) -> list:
        import json, re

        def extract_and_parse(text: str):
            text = text.strip()

            # Step 1: remove markdown code fences
            text = re.sub(r"```(?:json)?\s*", "", text)
            text = re.sub(r"```", "", text)
            text = text.strip()

            # Step 2: try direct parse (clean response)
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict):
                    for val in parsed.values():
                        if isinstance(val, list) and len(val) > 0:
                            return val
            except json.JSONDecodeError:
                pass

            # Step 3: find JSON array anywhere in the text
            array_match = re.search(r"\[[\s\S]*\]", text)
            if array_match:
                try:
                    parsed = json.loads(array_match.group())
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass

            # Step 4: find JSON object wrapping an array
            object_match = re.search(r"\{[\s\S]*\}", text)
            if object_match:
                try:
                    parsed = json.loads(object_match.group())
                    if isinstance(parsed, dict):
                        for val in parsed.values():
                            if isinstance(val, list) and len(val) > 0:
                                return val
                except json.JSONDecodeError:
                    pass

            # Step 5: collect individual objects line by line
            objects = re.findall(r"\{[^{}]+\}", text, re.DOTALL)
            if objects:
                results = []
                for obj_str in objects:
                    try:
                        obj = json.loads(obj_str)
                        if "start_time" in obj and "end_time" in obj:
                            results.append(obj)
                    except json.JSONDecodeError:
                        continue
                if results:
                    return results

            raise ValueError(f"No valid JSON found. Raw response: {text[:300]}")

        last_error = None
        for attempt in range(retries):
            try:
                result = extract_and_parse(raw)
                validated = []
                for item in result:
                    if (
                        isinstance(item, dict)
                        and "start_time" in item
                        and "end_time" in item
                    ):
                        item["start_time"] = float(item["start_time"])
                        item["end_time"] = float(item["end_time"])
                        item.setdefault("reason", "")
                        item.setdefault("virality_score", 7.0)
                        item.setdefault("hook", "")
                        validated.append(item)
                if validated:
                    return validated
                raise ValueError("JSON parsed but no valid highlight objects found.")
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    continue

        raise ValueError(
            f"Failed to parse AI response after {retries} attempts. "
            f"Last error: {last_error}"
        )

    def _extract_list(self, parsed: Any):
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict):
            for value in parsed.values():
                clips = self._extract_list(value)
                if clips is not None:
                    return clips
        if isinstance(parsed, str):
            for candidate in self._parse_candidates(parsed.strip()):
                clips = self._extract_list(candidate)
                if clips is not None:
                    return clips
        return None

    def _parse_candidates(self, text: str):
        candidates = []
        for candidate_text in self._candidate_strings(text):
            parsed = self._try_load(candidate_text)
            if parsed is not None:
                candidates.append(parsed)
        return candidates

    def _candidate_strings(self, text: str):
        candidates = [text]
        array_match = re.search(r"\[[\s\S]*\]", text)
        if array_match:
            candidates.append(array_match.group(0))
        object_match = re.search(r"\{[\s\S]*\}", text)
        if object_match:
            candidates.append(object_match.group(0))

        seen = set()
        unique = []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                unique.append(candidate)
        return unique

    def _try_load(self, text: str):
        if not text:
            return None
        loaders = [
            json.loads,
            ast.literal_eval,
        ]
        for loader in loaders:
            try:
                return loader(text)
            except Exception:
                continue
        return None

    def _normalize_clips(self, clips):
        normalized = []
        for clip in clips or []:
            if not isinstance(clip, dict):
                continue
            start_time = self._pick_float(
                clip,
                "start_time",
                "start",
                "startTime",
                "start_seconds",
                "from",
                "begin",
            )
            end_time = self._pick_float(
                clip,
                "end_time",
                "end",
                "endTime",
                "end_seconds",
                "to",
                "finish",
            )
            if start_time is None or end_time is None:
                range_start, range_end = self._pick_range(
                    clip,
                    "timestamp",
                    "timestamps",
                    "time_range",
                    "range",
                    "clip_range",
                    "segment",
                )
                if start_time is None:
                    start_time = range_start
                if end_time is None:
                    end_time = range_end
            if start_time is None or end_time is None or end_time <= start_time:
                continue
            normalized.append(
                {
                    "start_time": start_time,
                    "end_time": end_time,
                    "reason": str(
                        clip.get("reason")
                        or clip.get("why")
                        or clip.get("description")
                        or ""
                    ).strip(),
                    "virality_score": clip.get(
                        "virality_score", clip.get("score", "N/A")
                    ),
                    "hook": str(clip.get("hook") or "").strip(),
                }
            )
        if not normalized:
            raise RuntimeError("no_valid_clips")
        normalized.sort(key=lambda item: item["start_time"])
        return normalized

    def _pick_float(self, data, *keys):
        for key in keys:
            if key not in data:
                continue
            value = self._to_float(data.get(key))
            if value is not None:
                return value
        return None

    def _pick_range(self, data, *keys):
        for key in keys:
            if key not in data:
                continue
            value = data.get(key)
            start_time, end_time = self._to_range(value)
            if start_time is not None and end_time is not None:
                return start_time, end_time
        return None, None

    def _to_float(self, value):
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            pass

        if isinstance(value, str):
            text = value.strip().strip("[](){}")
            if not text:
                return None

            colon_seconds = self._timestamp_to_seconds(text)
            if colon_seconds is not None:
                return colon_seconds

            match = re.search(r"-?\d+(?:\.\d+)?", text)
            if match:
                try:
                    return float(match.group(0))
                except ValueError:
                    return None
        return None

    def _to_range(self, value):
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            start_time = self._to_float(value[0])
            end_time = self._to_float(value[1])
            return start_time, end_time

        if isinstance(value, str):
            text = value.strip().strip("[](){}")
            parts = re.split(r"\s*(?:->|–|—|-|to)\s*", text)
            if len(parts) >= 2:
                start_time = self._to_float(parts[0])
                end_time = self._to_float(parts[1])
                return start_time, end_time
        return None, None

    def _timestamp_to_seconds(self, text):
        if ":" not in text:
            return None
        parts = text.split(":")
        if not all(part.strip().isdigit() for part in parts):
            return None
        try:
            nums = [int(part.strip()) for part in parts]
        except ValueError:
            return None
        if len(nums) == 2:
            mins, secs = nums
            return float(mins * 60 + secs)
        if len(nums) == 3:
            hours, mins, secs = nums
            return float(hours * 3600 + mins * 60 + secs)
        return None

    def _friendly_error(self, code: str):
        if code in ERROR_MESSAGES:
            return ERROR_MESSAGES[code]

        for prefix, label in (
            ("groq_api:", "Groq"),
            ("gemini_api:", "Gemini"),
            ("openrouter_api:", "OpenRouter"),
            ("ollama_api:", "Ollama"),
        ):
            if code.startswith(prefix):
                detail = code[len(prefix) :].strip() or "Unknown provider error."
                return f"❌ {label} error: {detail}"

        return "❌ AI highlight detection failed. Try again or switch provider."
