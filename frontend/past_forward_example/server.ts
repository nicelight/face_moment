/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import express from "express";
import path from "path";
import { createServer as createViteServer } from "vite";
import { GoogleGenAI } from "@google/genai";
import type { GenerateContentResponse } from "@google/genai";

async function startServer() {
  const app = express();
  const PORT = 3000;

  // Increase payload limit for base64 image uploads
  app.use(express.json({ limit: "50mb" }));
  app.use(express.urlencoded({ limit: "50mb", extended: true }));

  // API endpoint for image generation
  app.post("/api/generate", async (req, res): Promise<any> => {
    try {
      const { imageDataUrl, decade } = req.body;

      if (!imageDataUrl) {
         return res.status(400).json({ error: "No image source uploaded." });
      }

      if (!decade) {
         return res.status(400).json({ error: "No decade specified." });
      }

      const activeApiKey = process.env.GEMINI_API_KEY || process.env.API_KEY;
      if (!activeApiKey) {
         return res.status(503).json({ 
           error: "API key is not configured. Please add your GEMINI_API_KEY in Settings > Secrets." 
         });
      }

      const activeAi = new GoogleGenAI({
        apiKey: activeApiKey,
        httpOptions: {
          headers: {
            "User-Agent": "aistudio-build",
          },
        },
      });

      const match = imageDataUrl.match(/^data:(image\/\w+);base64,(.*)$/);
      if (!match) {
         return res.status(400).json({ error: "Invalid image format. Must be a valid image Data URL." });
      }
      const [, mimeType, base64Data] = match;

      const imagePart = {
        inlineData: { mimeType, data: base64Data },
      };

      const primaryPrompt = `Reimagine the person in this photo in the style of the ${decade}. This includes clothing, hairstyle, photo quality, and the overall aesthetic of that decade. The output must be a photorealistic image showing the person clearly.`;
      const fallbackPrompt = `Create a photograph of the person in this image as if they were living in the ${decade}. The photograph should capture the distinct fashion, hairstyles, and overall atmosphere of that time period. Ensure the final image is a clear photograph that looks authentic to the era.`;

      console.log(`[Backend] Generating image for decade: ${decade}`);

      // Call Gemini helper with retry
      const callGeminiWithRetry = async (prompt: string): Promise<GenerateContentResponse> => {
        const maxRetries = 3;
        const initialDelay = 1000;

        for (let attempt = 1; attempt <= maxRetries; attempt++) {
          try {
            return await activeAi.models.generateContent({
              model: "gemini-2.5-flash-image",
              contents: { parts: [imagePart, { text: prompt }] },
            });
          } catch (error: any) {
            console.error(`[Backend] Error calling Gemini (Attempt ${attempt}/${maxRetries}):`, error);
            const errorMessage = error instanceof Error ? error.message : JSON.stringify(error);
            const isAuthOrValidationIssue = 
              errorMessage.includes("API_KEY_INVALID") || 
              errorMessage.includes("INVALID_ARGUMENT") || 
              errorMessage.includes("PERMISSION_DENIED");

            if (!isAuthOrValidationIssue && attempt < maxRetries) {
              const delay = initialDelay * Math.pow(2.5, attempt - 1) + Math.random() * 500;
              console.log(`[Backend] Standard or Quota error detected. Retrying in ${Math.round(delay)}ms...`);
              await new Promise(resolve => setTimeout(resolve, delay));
              continue;
            }
            throw error;
          }
        }
        throw new Error("Gemini API call failed after retries.");
      };

      const processResponse = (response: GenerateContentResponse): string => {
        const imagePartFromResponse = response.candidates?.[0]?.content?.parts?.find(part => part.inlineData);

        if (imagePartFromResponse?.inlineData) {
          const { mimeType: outMimeType, data: outData } = imagePartFromResponse.inlineData;
          return `data:${outMimeType};base64,${outData}`;
        }

        const textResponse = response.text || "";
        console.error("[Backend] API text response received instead of image:", textResponse);
        throw new Error(`Model returned text: "${textResponse.substring(0, 100)}..."`);
      };

      // Try primary prompt first
      try {
        const response = await callGeminiWithRetry(primaryPrompt);
        const url = processResponse(response);
        return res.json({ url });
      } catch (err: any) {
        console.warn(`[Backend] Primary prompt failed for ${decade}, trying fallback. Error:`, err.message);
        
        // Try fallback prompt
        try {
          const fallbackResponse = await callGeminiWithRetry(fallbackPrompt);
          const url = processResponse(fallbackResponse);
          return res.json({ url });
        } catch (fallbackErr: any) {
          console.error(`[Backend] Fallback also failed for ${decade}:`, fallbackErr.message);
          return res.status(500).json({ 
            error: `Failed to generate image. Details: ${fallbackErr.message || "Unknown error"}` 
          });
        }
      }
    } catch (globalErr: any) {
      console.error("[Backend] Unhandled API error:", globalErr);
      return res.status(500).json({ error: globalErr.message || "An unexpected server error occurred." });
    }
  });

  // Vite middleware setup in development, static serve in production
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*all", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`[Backend] Server running on http://localhost:${PORT} in ${process.env.NODE_ENV || "development"} mode`);
  });
}

startServer();
