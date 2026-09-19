"use client";

import Image from "next/image";
import { MutableRefObject, useEffect, useRef, useState } from "react";

/** 부모가 녹음을 켜고 끌 수 있게 넘겨주는 핸들.
 *  `stop`은 3.0-c의 정지 버튼이, `start`는 홈의 마이크 버튼으로 들어온 경우
 *  (`/record?voice=1`)가 쓴다. */
export interface VoiceControls {
  start: () => void;
  stop: () => void;
}

interface VoiceInputProps {
  /** 최종(또는 onend 시점까지 모인) 인식 결과를 텍스트 입력과 동일한 제출 경로로 넘긴다. */
  onTranscript: (text: string) => void;
  /** 부모가 이미 제출 처리 중이면(스켈레톤 표시 중) 마이크 버튼도 눌리지 않게 한다. */
  disabled?: boolean;
  /**
   * "labeled" — 텍스트 라벨이 붙은 알약 버튼.
   * "icon" — Figma 3.1/3.3의 입력창 우하단 원형 버튼(44×44, `icon/mic` 20px).
   */
  variant?: "labeled" | "icon";
  /**
   * 녹음 상태를 부모에게 올려준다 (9/18 신규 — Figma "3.0-c 음성 녹음 중").
   *
   * 녹음 중 화면은 **입력창 자리를 통째로 대체**하는 상태라 이 컴포넌트가 혼자
   * 그릴 수 없다(버튼은 입력창 안에 있다). 인식 엔진은 여기가 계속 들고 있고,
   * 그리는 건 부모가 한다 — 상태와 정지 핸들만 넘긴다.
   */
  onListeningChange?: (listening: boolean) => void;
  onInterimChange?: (text: string) => void;
  controlsRef?: MutableRefObject<VoiceControls | null>;
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
export function VoiceInput({
  onTranscript,
  disabled = false,
  variant = "labeled",
  onListeningChange,
  onInterimChange,
  controlsRef,
}: VoiceInputProps) {
  // SSR과 첫 클라이언트 렌더를 일치시키기 위해 "지원됨"으로 시작하고, 마운트 후
  // 실제 지원 여부를 확인해 갱신한다 (하이드레이션 불일치 방지).
  const [supported, setSupported] = useState(true);
  const [listening, setListening] = useState(false);
  const [interimText, setInterimText] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  /**
   * 정지를 누른 뒤 `onend`가 올 때까지의 짧은 구간 (9/19 신규).
   *
   * **왜 필요한가**: `recognition.stop()`은 즉시 끝나지 않는다 — 음성 인식 서비스가
   * 마지막 결과를 돌려준 뒤에야 `onend`가 온다. 그 사이 화면을 녹음 상태로 두면
   * 정지를 눌러도 아무 반응이 없는 것처럼 보인다(사용자 신고, 9/19). 그래서 화면은
   * **누르는 즉시** 녹음 상태에서 빠져나오고, 실제 종료는 여기서 따로 기억한다 —
   * 종료 전에 마이크를 다시 누르면 "recognition has already started"로 터진다.
   */
  const [stopping, setStopping] = useState(false);
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

  // `onend`가 끝내 오지 않는 경우에 대비한 안전장치 — 안 풀면 마이크 버튼이 영원히
  // 비활성으로 남는다. 정상 경로에서는 보통 1초 안에 onend가 와서 먼저 해제된다.
  useEffect(() => {
    if (!stopping) return;
    const timer = setTimeout(() => setStopping(false), 5000);
    return () => clearTimeout(timer);
  }, [stopping]);

  // 상태를 부모에게도 같이 알린다 — setState와 콜백이 갈라지지 않게 한 곳에 묶는다.
  const beginListening = () => {
    setListening(true);
    onListeningChange?.(true);
  };
  const endListening = () => {
    setListening(false);
    setStopping(false);
    onListeningChange?.(false);
  };
  const pushInterim = (text: string) => {
    setInterimText(text);
    onInterimChange?.(text);
  };

  const handleClick = () => {
    if (disabled || listening || stopping) return;

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
      pushInterim("");
    };

    beginListening();
    setStatusMessage(null);
    pushInterim("");

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
        pushInterim(transcript);
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
      endListening();
      recognitionRef.current = null;
      // Chrome은 isFinal 결과 없이 조용히 onend로 끝나는 경우가 있다 — 그때까지 모인
      // 텍스트로 대신 제출한다 (submitted 플래그로 중복 제출 방지, 9/11에 실사용 중 발견된 버그).
      submit(latestTranscript);
    };

    recognition.start();
  };

  /**
   * 부모(3.0-c 정지 버튼 / 홈의 마이크로 들어온 경우)가 쓰는 핸들.
   *
   * 의존성 배열을 두지 않아 **매 렌더마다 최신 핸들러로 다시 붙는다** — 한 번만
   * 붙이면 `listening`/`disabled` 같은 값이 첫 렌더 시점으로 굳어버린다.
   */
  useEffect(() => {
    if (!controlsRef) return;
    const ref = controlsRef;
    ref.current = {
      start: handleClick,
      stop: () => {
        // 화면은 **누르는 즉시** 녹음 상태에서 빠져나온다. `recognition.stop()`은
        // 음성 인식 서비스가 마지막 결과를 돌려준 뒤에야 `onend`를 주기 때문에,
        // 그걸 기다리면 정지를 눌러도 반응이 없는 것처럼 보인다(9/19 사용자 신고).
        // `stop()`이라 그때까지 모인 텍스트는 정상 제출된다(abort()는 버려진다).
        if (!recognitionRef.current) return;
        setStopping(true);
        setListening(false);
        onListeningChange?.(false);
        recognitionRef.current.stop();
      },
    };
    return () => {
      ref.current = null;
    };
  });

  if (!supported) {
    return (
      <p className="text-xs text-zinc-400">
        이 브라우저는 음성 입력을 지원하지 않습니다 (Chrome 권장). 텍스트로 입력해 주세요.
      </p>
    );
  }

  if (variant === "icon") {
    // Figma 3.1/3.3 (`299:12251`): 44×44 원형, 배경 `text/1`, `icon/mic` 20px.
    // 인식 중 상태 텍스트는 여기서 그리지 않는다 — 부모가 3.0-c 화면으로 그린다.
    // 다만 마이크 권한 거부는 반드시 보여야 해서(목업엔 없는 상태) 남겨 둔다.
    return (
      <div className="flex flex-col items-end gap-1">
        <button
          type="button"
          onClick={handleClick}
          disabled={disabled || listening || stopping}
          aria-label={listening ? "듣고 있어요" : "음성 입력"}
          className="flex size-[44px] shrink-0 items-center justify-center rounded-full bg-[#ede9e2] transition-opacity active:opacity-80 disabled:opacity-50"
        >
          <Image src="/icons/mic.svg" alt="" width={20} height={20} aria-hidden />
        </button>

        {statusMessage && (
          <p className="max-w-[220px] text-right text-[11px] text-red-400">{statusMessage}</p>
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
