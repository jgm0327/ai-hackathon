/**
 * Web Speech API (`SpeechRecognition`) 최소 타입 선언.
 *
 * TypeScript의 `lib.dom.d.ts`(5.9 기준)에는 `SpeechRecognitionAlternative` /
 * `SpeechRecognitionResult` / `SpeechRecognitionResultList`만 있고, 정작 인식기
 * 본체(`SpeechRecognition`)와 이벤트 타입, `window.webkitSpeechRecognition`
 * 벤더 프리픽스는 빠져 있다. 여기서 그 나머지만 보충한다
 * (기존 lib.dom 타입과 겹치지 않도록 `results`는 `SpeechRecognitionResultList`를 그대로 재사용).
 *
 * 참고: `web/components/VoiceInput.tsx` (`docs/06-migration.md` §2.1 포팅).
 */

export {};

declare global {
  interface SpeechRecognitionErrorEvent extends Event {
    readonly error: string;
    readonly message: string;
  }

  interface SpeechRecognitionEvent extends Event {
    readonly resultIndex: number;
    readonly results: SpeechRecognitionResultList;
  }

  interface SpeechRecognition extends EventTarget {
    lang: string;
    continuous: boolean;
    interimResults: boolean;
    maxAlternatives: number;
    start(): void;
    stop(): void;
    abort(): void;
    onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => void) | null;
    onerror: ((this: SpeechRecognition, ev: SpeechRecognitionErrorEvent) => void) | null;
    onend: ((this: SpeechRecognition, ev: Event) => void) | null;
    onstart: ((this: SpeechRecognition, ev: Event) => void) | null;
  }

  interface SpeechRecognitionConstructor {
    new (): SpeechRecognition;
  }

  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}
