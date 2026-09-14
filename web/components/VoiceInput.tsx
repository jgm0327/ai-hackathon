"use client";

import { useEffect, useRef, useState } from "react";

interface VoiceInputProps {
  /** 최종(또는 onend 시점까지 모인) 인식 결과를 텍스트 입력과 동일한 제출 경로로 넘긴다. */
  onTranscript: (text: string) => void;
  /** 부모가 이미 제출 처리 중이면(스켈레톤 표시 중) 마이크 버튼도 눌리지 않게 한다. */
  disabled?: boolean;
  /**
   * "labeled" — 텍스트 라벨이 붙은 알약 버튼(기존 기본값).
   * "icon" — Figma "3.0 일지 기록 패드" 대응: 입력창 우하단에 얹는 원형 아이콘
   * 버튼(`size-[40px]`), 라벨 없음. 인식/에러 상태 텍스트는 버튼 아래 작게 표시.
   */
  variant?: "labeled" | "icon";
}

/**
 * 음성으로 한 줄 기록하기 — `src/frontend/components/voice_input.py`의 JS 로직을
 * React로 그대로 포팅한 것 (`docs/06-migration.md` §2.1).
 *
 * Streamlit 시절엔 `components.html()` iframe 안에서 인식 결과를 base64 쿼리 파라미터에
 * 실어 페이지 전체를 리다이렉트해야 했지만(iframe 밖 Python으로 값을 넘길 방법이
 * 그것뿐이었음), Next.js에서는 이 컴포넌트가 페이지의 진짜 일부이므로 그럴 필요가
 * 없다 — 인식 결과를 그냥 React state로 들고 있다가 `onTranscript` 콜백으로 넘긴다.
 *
 * 텍스트 입력과 "같은 제출 경로"를 타야 하므로 이 컴포넌트 자신은 결과 카드/스켈레톤을
 * 렌더링하지 않는다 — 그건 부모(`app/page.tsx`)가 텍스트 제출과 동일하게 처리한다.
 */
export function VoiceInput({ onTranscript, disabled = false, variant = "labeled" }: VoiceInputProps) {
  // SSR과 첫 클라이언트 렌더를 일치시키기 위해 "지원됨"으로 시작하고, 마운트 후
  // 실제 지원 여부를 확인해 갱신한다 (하이드레이션 불일치 방지).
  const [supported, setSupported] = useState(true);
  const [listening, setListening] = useState(false);
  const [interimText, setInterimText] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  useEffect(() => {
    const ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    // 마운트 직후 1회, 실제 브라우저 지원 여부로 초기 낙관값을 갱신하는 표준 패턴
    // (lib/useProjects.ts의 최초 로드와 동일한 이유로 억제).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSupported(!!ctor);
  }, []);

  // 언마운트 시 인식이 남아있으면 정리 (예: 페이지 이동).
  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
    };
  }, []);

  const handleClick = () => {
    if (disabled || listening) return;

    const RecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!RecognitionCtor) {
      setSupported(false);
      return;
    }

    const recognition = new RecognitionCtor();
    recognition.lang = "ko-KR";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognitionRef.current = recognition;

    let latestTranscript = "";
    let submitted = false;

    const submit = (transcript: string) => {
      if (submitted) return;
      const trimmed = transcript.trim();
      if (!trimmed) return;
      submitted = true;
      onTranscript(trimmed);
      setInterimText("");
    };

    setListening(true);
    setStatusMessage(null);
    setInterimText("");

    recognition.onresult = (event) => {
      let transcript = "";
      for (let i = 0; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      latestTranscript = transcript;
      const lastResult = event.results[event.results.length - 1];

      if (lastResult.isFinal) {
        submit(transcript);
      } else {
        setInterimText(transcript);
      }
    };

    recognition.onerror = (event) => {
      if (event.error === "not-allowed") {
        setStatusMessage("마이크 권한이 거부됐습니다. 브라우저 설정에서 권한을 허용해 주세요.");
      } else if (event.error === "no-speech" || event.error === "aborted") {
        // 놀랄 필요 없는 상황 — 조용히 버튼만 다시 활성화한다.
      } else {
        setStatusMessage(`음성 인식에 실패했습니다: ${event.error}`);
      }
    };

    recognition.onend = () => {
      setListening(false);
      recognitionRef.current = null;
      // Chrome은 isFinal 결과 없이 조용히 onend로 끝나는 경우가 있다 — 그때까지 모인
      // 텍스트로 대신 제출한다 (submitted 플래그로 중복 제출 방지, 9/11에 실사용 중 발견된 버그).
      submit(latestTranscript);
    };

    recognition.start();
  };

  if (!supported) {
    return (
      <p className="text-xs text-zinc-400">
        이 브라우저는 음성 입력을 지원하지 않습니다 (Chrome 권장). 텍스트로 입력해 주세요.
      </p>
    );
  }

  if (variant === "icon") {
    return (
      <div className="flex flex-col items-end gap-1">
        <button
          type="button"
          onClick={handleClick}
          disabled={disabled || listening}
          aria-label={listening ? "듣고 있어요" : "음성 입력"}
          className={`flex size-[40px] shrink-0 items-center justify-center rounded-full text-base transition-colors active:scale-[0.95] disabled:opacity-50 ${
            listening
              ? "bg-[#18181b] text-white hover:bg-zinc-800"
              : "bg-[#f4f4f5] text-[#6b7280] hover:bg-[#e4e4e7]"
          }`}
        >
          <span aria-hidden>🎙️</span>
        </button>

        {listening && (
          <p className="max-w-[220px] text-right text-[11px] text-[#a1a1aa]">
            {interimText ? `인식 중: ${interimText}` : "듣고 있어요…"}
          </p>
        )}

        {statusMessage && (
          <p className="max-w-[220px] text-right text-[11px] text-red-600">{statusMessage}</p>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled || listening}
        className="inline-flex w-fit items-center gap-1.5 rounded-full border border-zinc-200 bg-white px-3.5 py-2 text-sm font-medium text-zinc-700 shadow-sm transition-colors hover:bg-zinc-50 active:scale-[0.98] disabled:opacity-50"
      >
        <span aria-hidden>🎤</span>
        {listening ? "듣고 있어요…" : "말로 기록하기"}
      </button>

      {listening && (
        <p className="text-xs text-zinc-500">
          {interimText ? `인식 중: ${interimText}` : "퇴근길에 오늘 한 일을 말해보세요."}
        </p>
      )}

      {statusMessage && <p className="text-xs text-red-600">{statusMessage}</p>}
    </div>
  );
}
