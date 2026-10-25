"use client";

import { useEffect, useMemo, useState } from "react";
import {
  renderShareImage,
  type ShareImageInput,
  type ShareTextTheme,
} from "@/lib/shareImage";

type Props = {
  data: ShareImageInput;
  label?: string;
};

function fileName(data: ShareImageInput): string {
  const key = data.date || data.weekStart || data.kind;
  return `fantasy-${data.kind}-${key.replace(/[^a-zA-Z0-9-]/g, "-")}.png`;
}

export default function ShareButton({ data, label = "Поделиться" }: Props) {
  const [open, setOpen] = useState(false);
  const [square, setSquare] = useState(false);
  const [textTheme, setTextTheme] = useState<ShareTextTheme>("light");
  const [includeName, setIncludeName] = useState(false);
  const [includeLeagueRank, setIncludeLeagueRank] = useState(false);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [canShareFiles, setCanShareFiles] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const dataSignature = JSON.stringify(data);
  const imageInput = useMemo(() => {
    const stableData = JSON.parse(dataSignature) as ShareImageInput;
    return {
      ...stableData,
      userName: includeName ? stableData.userName : undefined,
    };
  }, [dataSignature, includeName]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    let url = "";

    renderShareImage(imageInput, {
      square,
      textTheme,
      includeName,
      includeLeagueRank,
    }).then((rendered) => {
      if (cancelled) return;
      url = URL.createObjectURL(rendered);
      setBlob(rendered);
      setPreviewUrl(url);
      try {
        const file = new File([rendered], fileName(imageInput), { type: "image/png" });
        setCanShareFiles(Boolean(navigator.canShare?.({ files: [file] })));
      } catch {
        setCanShareFiles(false);
      }
    }).catch((renderError: unknown) => {
      if (!cancelled) {
        setError(renderError instanceof Error ? renderError.message : "Не удалось создать изображение.");
      }
    }).finally(() => {
      if (!cancelled) setBusy(false);
    });

    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [open, imageInput, square, textTheme, includeName, includeLeagueRank]);

  const resetPreviewForRender = () => {
    setBusy(true);
    setError("");
    setBlob(null);
    setPreviewUrl("");
    setCanShareFiles(false);
  };

  const openDialog = () => {
    resetPreviewForRender();
    setOpen(true);
  };

  const download = () => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileName(imageInput);
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const share = async () => {
    if (!blob) return;
    setError("");
    try {
      const file = new File([blob], fileName(imageInput), { type: "image/png" });
      if (!navigator.canShare?.({ files: [file] }) || !navigator.share) {
        setError("Системный шеринг не поддерживается этим браузером.");
        return;
      }
      await navigator.share({ files: [file], title: "fantasy." });
    } catch (shareError: unknown) {
      if (shareError instanceof Error && shareError.name === "AbortError") return;
      setError("Не удалось открыть системное меню «Поделиться».");
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={openDialog}
        className="inline-flex items-center justify-center gap-2 border-2 border-black bg-white px-3 py-2 text-[10px] font-bold uppercase tracking-widest transition-colors hover:bg-[#ffd500] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2]"
      >
        <span aria-hidden="true">↗</span>{label}
      </button>
      {open && (
        <div
          className="fixed inset-0 z-[140] flex items-end justify-center bg-black/65 p-0 sm:items-center sm:p-4"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setOpen(false);
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="share-image-dialog-title"
            data-lenis-prevent
            className="max-h-[94dvh] w-full max-w-xl overflow-y-auto border-2 border-black bg-[#f4f4f0] text-[#111] shadow-[6px_6px_0_#111] sm:max-h-[90dvh]"
          >
            <header className="flex items-center justify-between gap-3 border-b-2 border-black bg-[#ffd500] px-4 py-3">
              <h2 id="share-image-dialog-title" className="font-display text-xl uppercase">Поделиться</h2>
              <button type="button" onClick={() => setOpen(false)} aria-label="Закрыть окно шаринга" className="h-9 w-9 border-2 border-black bg-white text-lg font-bold">×</button>
            </header>
            <div className="space-y-4 p-4">
              <div
                className="mx-auto flex max-h-[42dvh] min-h-48 w-full items-center justify-center overflow-hidden border-2 border-black/20"
                style={{
                  backgroundColor: "#fff",
                  backgroundImage: "linear-gradient(45deg,#d8d8d8 25%,transparent 25%),linear-gradient(-45deg,#d8d8d8 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#d8d8d8 75%),linear-gradient(-45deg,transparent 75%,#d8d8d8 75%)",
                  backgroundSize: "20px 20px",
                  backgroundPosition: "0 0,0 10px,10px -10px,-10px 0",
                }}
              >
                {busy && <p className="text-sm font-bold">Готовим PNG…</p>}
                {!busy && previewUrl && (
                  // The checkerboard is UI only; the PNG itself stays transparent.
                  <img src={previewUrl} alt="Предпросмотр прозрачного изображения для публикации" className="max-h-[42dvh] max-w-full object-contain" />
                )}
                {!busy && !previewUrl && error && <p role="alert" className="p-4 text-sm font-bold">{error}</p>}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <label className="flex items-center gap-2 border-2 border-black bg-white p-2 text-xs font-bold">
                  <input type="checkbox" checked={square} onChange={(event) => { resetPreviewForRender(); setSquare(event.target.checked); }} />
                  Квадрат 1080×1080
                </label>
                <label className="flex items-center gap-2 border-2 border-black bg-white p-2 text-xs font-bold">
                  <input type="checkbox" checked={includeName} onChange={(event) => { resetPreviewForRender(); setIncludeName(event.target.checked); }} disabled={!data.userName} />
                  Добавить имя
                </label>
                {data.leagueRank != null && data.kind === "week" && (
                  <label className="col-span-2 flex items-center gap-2 border-2 border-black bg-white p-2 text-xs font-bold">
                    <input type="checkbox" checked={includeLeagueRank} onChange={(event) => { resetPreviewForRender(); setIncludeLeagueRank(event.target.checked); }} />
                    Добавить место в лиге
                  </label>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="mr-1 text-[10px] font-bold uppercase tracking-widest text-[#666]">Текст</span>
                <button type="button" aria-pressed={textTheme === "light"} onClick={() => { if (textTheme !== "light") { resetPreviewForRender(); setTextTheme("light"); } }} className={`border-2 border-black px-3 py-2 text-xs font-bold ${textTheme === "light" ? "bg-black text-white" : "bg-white"}`}>Светлый</button>
                <button type="button" aria-pressed={textTheme === "dark"} onClick={() => { if (textTheme !== "dark") { resetPreviewForRender(); setTextTheme("dark"); } }} className={`border-2 border-black px-3 py-2 text-xs font-bold ${textTheme === "dark" ? "bg-black text-white" : "bg-white"}`}>Тёмный</button>
              </div>
              {error && <p role="alert" className="text-sm font-bold text-[#b91c1c]">{error}</p>}
              <div className="flex flex-wrap gap-2">
                <button type="button" disabled={!blob || busy} onClick={download} className="flex-1 border-2 border-black bg-[#ff4b26] px-4 py-3 text-xs font-bold uppercase tracking-widest text-white hover:bg-black disabled:opacity-50">Скачать PNG</button>
                {canShareFiles && <button type="button" disabled={!blob || busy} onClick={() => void share()} className="flex-1 border-2 border-black bg-[#5866f2] px-4 py-3 text-xs font-bold uppercase tracking-widest text-white hover:bg-black disabled:opacity-50">Системный шеринг</button>}
              </div>
              <p className="text-[10px] text-[#666]">Изображение создаётся локально в браузере. Файл не отправляется на сервер.</p>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
