// Public camera JPEG/history only. Stored captures never become search input.
// @docs .memory-bank/features/FT-013.md#FT-013-AC-001
export function selfieDimensions(width, height) {
  const scale = Math.min(1, 960 / Math.max(width, height));
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

export async function encodeSelfie(video, canvas = document.createElement("canvas")) {
  const dimensions = selfieDimensions(video.videoWidth, video.videoHeight);
  canvas.width = dimensions.width; canvas.height = dimensions.height;
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", .85));
  if (!blob) throw new Error("capture_failed");
  return blob;
}

export function saveSelfie(blob) {
  return new Promise((resolve, reject) => {
    let blocked = false;
    const request = indexedDB.open("face-moment-selfies", 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore("captures", { keyPath: "id", autoIncrement: true });
    };
    request.onerror = () => reject(request.error);
    request.onblocked = () => { blocked = true; reject(new Error("selfie_history_unavailable")); };
    request.onsuccess = () => {
      const db = request.result;
      if (blocked) { db.close(); return; }
      let transaction;
      try {
        transaction = db.transaction("captures", "readwrite");
        transaction.oncomplete = () => { db.close(); resolve(); };
        transaction.onabort = () => { db.close(); reject(transaction.error ?? new Error("selfie_history_unavailable")); };
        transaction.objectStore("captures").add({ blob, capturedAt: new Date().toISOString() });
      } catch (error) {
        transaction?.abort(); db.close(); reject(error);
      }
    };
  });
}
