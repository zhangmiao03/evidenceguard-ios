import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import { timeLabel, type Evidence } from "./product-types";

export function Modal({
  title,
  children,
  onClose,
  busy = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    return () => {
      ref.current?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="product-dialog"
      aria-labelledby={id}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      <div className="section-heading">
        <h2 id={id}>{title}</h2>
        <button
          className="text-button"
          aria-label="关闭窗口"
          disabled={busy}
          onClick={onClose}
        >
          关闭
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function ImageEvidence({ path, alt }: { path: string; alt: string }) {
  const [url, setURL] = useState("");
  const [error, setError] = useState(false);
  useEffect(() => {
    setURL("");
    setError(false);
    let alive = true,
      resource = "";
    void api
      .media(path)
      .then((value) => {
        resource = value;
        if (alive) setURL(value);
        else URL.revokeObjectURL(value);
      })
      .catch(() => {
        if (alive) setError(true);
      });
    return () => {
      alive = false;
      if (resource) URL.revokeObjectURL(resource);
    };
  }, [path]);
  return url ? (
    <img className="evidence-image" src={url} alt={alt} />
  ) : (
    <div className="image-unavailable">
      {error ? "图片暂时无法读取" : "图片加载中…"}
    </div>
  );
}

export function VideoPlayer({
  path,
  offset = 0,
}: {
  path: string;
  offset?: number;
}) {
  const [url, setURL] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true,
      resource = "";
    setURL("");
    setError("");
    // Fetch with the team header, including on local HTTP where Secure media
    // cookies cannot be set. A blob URL never contains credentials.
    void api
      .media(path, 120000)
      .then((value) => {
        resource = value;
        if (alive) setURL(value);
        else URL.revokeObjectURL(value);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
      if (resource) URL.revokeObjectURL(resource);
    };
  }, [path]);
  return (
    <div className="video-playback">
      {error ? (
        <p role="alert">{error}</p>
      ) : url ? (
        <>
          <video
            controls
            playsInline
            preload="metadata"
            src={url}
            onLoadedMetadata={(e) => {
              e.currentTarget.currentTime = Math.max(
                0,
                Math.min(offset, e.currentTarget.duration || offset),
              );
            }}
          />
          <a
            className="text-button"
            href={url}
            download="evidenceguard-recording.mp4"
          >
            下载片段
          </a>
        </>
      ) : (
        <p role="status">正在加载录像…</p>
      )}
    </div>
  );
}

export function EvidenceGallery({
  items,
  onSkill,
}: {
  items: Evidence[];
  onSkill: (id: string) => void;
}) {
  const [selected, setSelected] = useState<Evidence | null>(null);
  return (
    <section className="card product-card">
      <div className="section-heading">
        <h2>证据库</h2>
        <span>团队空间 · {items.length} 条</span>
      </div>
      {!items.length && (
        <p className="empty-inline">
          暂时没有证据，完成的观察会保留来源与时间。
        </p>
      )}
      <div className="evidence-grid">
        {items.map((item) => (
          <article key={item.id} className="evidence-tile">
            {item.imageUrl && (
              <ImageEvidence path={item.imageUrl} alt="观察证据" />
            )}
            <strong>{item.deviceName || item.cameraId || "观察记录"}</strong>
            <p>{item.reason}</p>
            <small>
              {item.sourceType || "客户端取样"} ·{" "}
              {timeLabel(item.capturedAt || item.sampledAt)}
            </small>
            <div className="button-row">
              {item.skillId && (
                <button
                  className="text-button"
                  onClick={() => onSkill(item.skillId!)}
                >
                  查看任务
                </button>
              )}
              {item.videoUrl && (
                <button
                  className="text-button"
                  onClick={() => setSelected(item)}
                >
                  播放证据
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
      {selected?.videoUrl && (
        <Modal title="证据回看" onClose={() => setSelected(null)}>
          <p>{selected.reason}</p>
          <VideoPlayer path={selected.videoUrl} offset={selected.seekSeconds} />
        </Modal>
      )}
    </section>
  );
}

export function ErrorNotice({ error }: { error: string }) {
  return error ? (
    <p role="alert" className="notice error">
      {error}
    </p>
  ) : null;
}
