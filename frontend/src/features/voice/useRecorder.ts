import { useCallback, useEffect, useRef, useState } from "react";

import { concatenate, downsample, encodeWav } from "./wav";

export type RecorderState = "idle" | "requesting" | "recording" | "denied" | "unsupported" | "error";

type AudioContextConstructor = typeof AudioContext;

function audioContextClass(): AudioContextConstructor | undefined {
  if (typeof window === "undefined") return undefined;
  return window.AudioContext ?? (window as unknown as { webkitAudioContext?: AudioContextConstructor }).webkitAudioContext;
}

/**
 * Recording is possible only in a secure context (HTTPS or localhost) with
 * getUserMedia and Web Audio. Phones opening the dev server over plain http on the
 * LAN are NOT secure contexts — they get the upload / typing fallbacks instead.
 */
export function recordingSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    window.isSecureContext === true &&
    typeof navigator !== "undefined" &&
    typeof navigator.mediaDevices?.getUserMedia === "function" &&
    Boolean(audioContextClass())
  );
}

interface Session {
  stream: MediaStream;
  context: AudioContext;
  processor: ScriptProcessorNode;
  source: MediaStreamAudioSourceNode;
  chunks: Float32Array[];
  startedAt: number;
}

/**
 * Push-to-talk recorder. Microphone permission is requested only when start() is
 * called. Stops automatically at `maxSeconds`. Produces a 16 kHz mono WAV Blob.
 */
export function useRecorder(maxSeconds: number) {
  const [state, setState] = useState<RecorderState>(() => (recordingSupported() ? "idle" : "unsupported"));
  const [elapsed, setElapsed] = useState(0);
  const [recording, setRecording] = useState<{ blob: Blob; seconds: number } | null>(null);
  const session = useRef<Session | null>(null);
  const timer = useRef<number | null>(null);

  const teardown = useCallback(() => {
    if (timer.current !== null) window.clearInterval(timer.current);
    timer.current = null;
    const current = session.current;
    session.current = null;
    if (!current) return null;
    current.processor.disconnect();
    current.source.disconnect();
    current.stream.getTracks().forEach((track) => track.stop());
    void current.context.close();
    return current;
  }, []);

  const stop = useCallback(() => {
    const finished = teardown();
    if (!finished) return;
    const samples = downsample(concatenate(finished.chunks), finished.context.sampleRate);
    const seconds = Math.min(samples.length / 16_000, maxSeconds);
    setRecording({ blob: encodeWav(samples.subarray(0, Math.floor(maxSeconds * 16_000))), seconds });
    setState("idle");
  }, [teardown, maxSeconds]);

  const start = useCallback(async () => {
    if (!recordingSupported()) {
      setState("unsupported");
      return;
    }
    setState("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      const Context = audioContextClass()!;
      const context = new Context();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const chunks: Float32Array[] = [];
      processor.onaudioprocess = (event) => chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      source.connect(processor);
      processor.connect(context.destination);
      session.current = { stream, context, processor, source, chunks, startedAt: Date.now() };
      setRecording(null);
      setElapsed(0);
      setState("recording");
      timer.current = window.setInterval(() => {
        const current = session.current;
        if (!current) return;
        const seconds = (Date.now() - current.startedAt) / 1000;
        setElapsed(seconds);
        if (seconds >= maxSeconds) stop();
      }, 200);
    } catch (error) {
      teardown();
      const name = (error as { name?: string })?.name;
      setState(name === "NotAllowedError" || name === "SecurityError" ? "denied" : "error");
    }
  }, [maxSeconds, stop, teardown]);

  const reset = useCallback(() => {
    teardown();
    setRecording(null);
    setElapsed(0);
    setState(recordingSupported() ? "idle" : "unsupported");
  }, [teardown]);

  useEffect(() => () => void teardown(), [teardown]);

  return { state, elapsed, recording, start, stop, reset };
}
