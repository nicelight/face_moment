/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Extracts the decade (e.g., "1950s") from a prompt string.
 * @param prompt The original prompt.
 * @returns The decade string or a fallback if not found.
 */
function extractDecade(prompt: string): string {
    const match = prompt.match(/(\d{4}s)/);
    return match ? match[1] : "1950s";
}

/**
 * Generates a decade-styled image from a source image by proxying the request which passes
 * through our robust, secure backend API endpoint. Keeping API keys hidden and safely operated.
 * @param imageDataUrl A data URL string of the source image (e.g., 'data:image/png;base64,...').
 * @param prompt The prompt containing the decade info.
 * @returns A promise that resolves to a base64-encoded image data URL of the generated image.
 */
export async function generateDecadeImage(imageDataUrl: string, prompt: string): Promise<string> {
    const decade = extractDecade(prompt);

    console.log(`[Client] Requesting reimaged picture for ${decade} via server API proxy...`);

    const response = await fetch("/api/generate", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            imageDataUrl,
            decade,
        }),
    });

    const contentType = response.headers.get("content-type");
    if (!contentType || !contentType.includes("application/json")) {
        const text = await response.text().catch(() => "");
        console.error("[Client] Non-JSON response received:", text.substring(0, 200));
        throw new Error(`The portal is briefly resolving or busy. Please try processing again in a few moments (Status ${response.status}).`);
    }

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const message = errorData.error || `HTTP error ${response.status}: ${response.statusText}`;
        throw new Error(message);
    }

    const data = await response.json();
    if (!data.url) {
        throw new Error("No image URL returned from the generation server.");
    }

    return data.url;
}
