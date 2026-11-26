import { ImagePlus, Trash2 } from "lucide-react";
import { type ChangeEvent, useEffect, useRef, useState } from "react";

import * as jobsApi from "../../api/jobs";
import { Alert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { useI18n } from "../../i18n/context";
import { describeError, LocalMessage } from "../../i18n/errors";

const MAX_PHOTOS = 5;
const MAX_BYTES = 5 * 1024 * 1024;

/** Private photo thumbnails, fetched with the session (never public URLs). */
function Thumbnail({ photo, label }: { photo: jobsApi.JobPhoto; label: string }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    jobsApi
      .fetchJobPhoto(photo.content_url)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [photo.content_url]);
  return url ? (
    <img src={url} alt={label} className="aspect-square w-full rounded-xl border border-line object-cover" />
  ) : (
    <div className="aspect-square w-full rounded-xl border border-line bg-surface" aria-label={label} />
  );
}

/**
 * Optional reference photos (≤ 5 JPEG/PNG/WebP, ≤ 5 MB each). The server re-checks every file and
 * removes location metadata. Photos are never sent to AI interpretation.
 */
export function JobPhotos({ jobId, photos, editable, onChange }: {
  jobId: string;
  photos: jobsApi.JobPhoto[];
  editable: boolean;
  onChange?: (photos: jobsApi.JobPhoto[]) => void;
}) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const files = [...(event.target.files ?? [])];
    event.target.value = "";
    setFailure(null);
    if (photos.length + files.length > MAX_PHOTOS) return setFailure(new LocalMessage("jobs.photos.tooMany"));
    if (files.some((file) => file.size > MAX_BYTES)) return setFailure(new LocalMessage("jobs.photos.tooLarge"));
    setBusy(true);
    let current = photos;
    try {
      for (const file of files) {
        const photo = await jobsApi.uploadJobPhoto(jobId, file, file.name);
        current = [...current, photo];
        onChange?.(current);
      }
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  }

  async function remove(photoId: string) {
    setFailure(null);
    try {
      await jobsApi.deleteJobPhoto(jobId, photoId);
      onChange?.(photos.filter((photo) => photo.id !== photoId));
    } catch (error) {
      setFailure(error);
    }
  }

  return (
    <div className="space-y-3">
      {photos.length > 0 && (
        <ul className="grid grid-cols-3 gap-2">
          {photos.map((photo, index) => (
            <li key={photo.id} className="space-y-1">
              <Thumbnail photo={photo} label={t("jobs.photos.alt", { number: index + 1 })} />
              {editable && (
                <Button variant="ghost" className="min-h-11 w-full text-sm" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => void remove(photo.id)}>
                  {t("jobs.photos.remove")}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}
      {editable && photos.length < MAX_PHOTOS && (
        <>
          <input ref={input} data-testid="job-photo-input" type="file" accept="image/jpeg,image/png,image/webp" multiple className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => void onFile(e)} />
          <Button variant="secondary" loading={busy} loadingLabel={t("jobs.photos.uploading")} icon={<ImagePlus className="size-5" aria-hidden />} onClick={() => input.current?.click()}>
            {t("jobs.photos.add", { remaining: MAX_PHOTOS - photos.length })}
          </Button>
        </>
      )}
    </div>
  );
}
