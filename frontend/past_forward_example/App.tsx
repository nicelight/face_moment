/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import React, { useState, ChangeEvent, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { generateDecadeImage } from './services/geminiService';
import PolaroidCard from './components/PolaroidCard';
import { createAlbumPage } from './lib/albumUtils';
import { cn } from './lib/utils';

const DECADES = ['1950s', '1960s', '1970s', '1980s', '1990s', '2000s'];

// Scattered positions for interactive light table on desktop
const POSITIONS = [
    { top: '8%', left: '10%', rotate: -8 },
    { top: '15%', left: '55%', rotate: 6 },
    { top: '48%', left: '6%', rotate: 4 },
    { top: '4%', left: '32%', rotate: 11 },
    { top: '42%', left: '68%', rotate: -12 },
    { top: '51%', left: '36%', rotate: -3 },
];

type ImageStatus = 'pending' | 'done' | 'error';
interface GeneratedImage {
    status: ImageStatus;
    url?: string;
    error?: string;
}

const useMediaQuery = (query: string) => {
    const [matches, setMatches] = useState(() => {
        if (typeof window !== "undefined") {
            return window.matchMedia(query).matches;
        }
        return false;
    });

    useEffect(() => {
        const media = window.matchMedia(query);
        const listener = (event: MediaQueryListEvent) => {
            setMatches(event.matches);
        };
        media.addEventListener('change', listener);
        setMatches(media.matches);
        return () => media.removeEventListener('change', listener);
    }, [query]);

    return matches;
};

/**
 * Utility to resize and compress any user uploaded image.
 * Resizes the image to fit within a given maximum bounding box,
 * and converts to a compressed JPEG data URL to minimize network payload,
 * avoid server out-of-memory errors, and run model inference quickly.
 */
function resizeAndCompressImage(file: File, maxDimension = 1000, quality = 0.85): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement('canvas');
                let width = img.width;
                let height = img.height;

                // Handle downscaling aspect ratio
                if (width > height) {
                    if (width > maxDimension) {
                        height = Math.round((height * maxDimension) / width);
                        width = maxDimension;
                    }
                } else {
                    if (height > maxDimension) {
                        width = Math.round((width * maxDimension) / height);
                        height = maxDimension;
                    }
                }

                canvas.width = width;
                canvas.height = height;

                const ctx = canvas.getContext('2d');
                if (!ctx) {
                    reject(new Error("Failed to get 2D context from canvas."));
                    return;
                }

                ctx.drawImage(img, 0, 0, width, height);
                const compressedDataUrl = canvas.toDataURL('image/jpeg', quality);
                resolve(compressedDataUrl);
            };
            img.onerror = () => {
                reject(new Error("Failed to load image elements. Image file might be corrupted."));
            };
            img.src = e.target?.result as string;
        };
        reader.onerror = () => {
            reject(new Error("Failed to read the upload file."));
        };
        reader.readAsDataURL(file);
    });
}

function App() {
    const [uploadedImage, setUploadedImage] = useState<string | null>(null);
    const [generatedImages, setGeneratedImages] = useState<Record<string, GeneratedImage>>({});
    const [isLoading, setIsLoading] = useState<boolean>(false);
    const [isDownloading, setIsDownloading] = useState<boolean>(false);
    const [appState, setAppState] = useState<'idle' | 'image-uploaded' | 'generating' | 'results-shown'>('idle');
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const dragAreaRef = useRef<HTMLDivElement>(null);
    const isMobile = useMediaQuery('(max-width: 768px)');

    // Mobile layout state options
    const [mobileViewMode, setMobileViewMode] = useState<'slider' | 'grid'>('slider');
    const [activeDecadeIndex, setActiveDecadeIndex] = useState<number>(0);

    const completedCount = Object.values(generatedImages).filter(
        img => img.status === 'done' || img.status === 'error'
    ).length;

    const handleImageUpload = async (e: ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            const file = e.target.files[0];
            try {
                const compressedDataUrl = await resizeAndCompressImage(file, 1000, 0.85);
                setUploadedImage(compressedDataUrl);
                setAppState('image-uploaded');
                setGeneratedImages({});
                setErrorMessage(null);
            } catch (err: any) {
                console.error("Failed to compress uploaded image:", err);
                setErrorMessage("Failed to process the uploaded photo. Please try a different image.");
            }
        }
    };

    const handleGenerateClick = async () => {
        if (!uploadedImage) return;

        setIsLoading(true);
        setAppState('results-shown');
        setActiveDecadeIndex(0);
        setErrorMessage(null);
        
        const initialImages: Record<string, GeneratedImage> = {};
        DECADES.forEach(decade => {
            initialImages[decade] = { status: 'pending' };
        });
        setGeneratedImages(initialImages);

        const decadesQueue = [...DECADES];
        let processedCount = 0;

        const processDecade = async (decade: string) => {
            try {
                if (processedCount > 0) {
                    // Stagger subsequent queries by 1.8 seconds to stay safe from rate blocks
                    await new Promise(resolve => setTimeout(resolve, 1800));
                }
                processedCount++;
                const prompt = `Reimagine the person in this photo in the style of the ${decade}. clothing, hairstyle, photo quality, and the overall aesthetic of that decade. photorealistic photograph of the person clearly.`;
                const resultUrl = await generateDecadeImage(uploadedImage, prompt);
                setGeneratedImages(prev => ({
                    ...prev,
                    [decade]: { status: 'done', url: resultUrl },
                }));
            } catch (err) {
                const errorStr = err instanceof Error ? err.message : "An unknown error occurred.";
                setGeneratedImages(prev => ({
                    ...prev,
                    [decade]: { status: 'error', error: errorStr },
                }));
                console.error(`Failed to generate image for ${decade}:`, err);
            }
        };

        // Run sequentially for robust stagger execution
        for (const dec of decadesQueue) {
            await processDecade(dec);
        }

        setIsLoading(false);
    };

    const handleRegenerateDecade = async (decade: string) => {
        if (!uploadedImage) return;

        if (generatedImages[decade]?.status === 'pending') {
            return;
        }

        setGeneratedImages(prev => ({
            ...prev,
            [decade]: { status: 'pending' },
        }));

        try {
            const prompt = `Reimagine the person in this photo in the style of the ${decade}. clothing, hairstyle, photo quality, and the overall aesthetic of that decade. photorealistic photograph of the person clearly.`;
            const resultUrl = await generateDecadeImage(uploadedImage, prompt);
            setGeneratedImages(prev => ({
                ...prev,
                [decade]: { status: 'done', url: resultUrl },
            }));
        } catch (err) {
            const errorStr = err instanceof Error ? err.message : "An unknown error occurred.";
            setGeneratedImages(prev => ({
                ...prev,
                [decade]: { status: 'error', error: errorStr },
            }));
            console.error(`Failed to regenerate image for ${decade}:`, err);
        }
    };
    
    const handleReset = () => {
        setUploadedImage(null);
        setGeneratedImages({});
        setAppState('idle');
        setMobileViewMode('slider');
        setActiveDecadeIndex(0);
        setErrorMessage(null);
    };

    const handleDownloadIndividualImage = (decade: string) => {
        const image = generatedImages[decade];
        if (image?.status === 'done' && image.url) {
            const link = document.createElement('a');
            link.href = image.url;
            link.download = `past-forward-${decade}.jpg`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
    };

    const handleDownloadAlbum = async () => {
        setIsDownloading(true);
        try {
            const imageData = Object.entries(generatedImages)
                .filter(([, image]) => image.status === 'done' && image.url)
                .reduce((acc, [decade, image]) => {
                    acc[decade] = image!.url!;
                    return acc;
                }, {} as Record<string, string>);

            if (Object.keys(imageData).length === 0) {
                setErrorMessage("No portraits are successfully developed yet.");
                return;
            }

            const albumDataUrl = await createAlbumPage(imageData);

            const link = document.createElement('a');
            link.href = albumDataUrl;
            link.download = 'past-forward-album.jpg';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } catch (error) {
            console.error("Failed to create or download album:", error);
            setErrorMessage("Failed to create the compilation page. Please try again.");
        } finally {
            setIsDownloading(false);
        }
    };

    return (
        <main className="h-[100dvh] w-full bg-[#0d0b0a] text-neutral-100 flex flex-col justify-between overflow-hidden relative select-none font-sans">
            {/* Background grid + ambient glows */}
            <div className="absolute inset-0 bg-grid-white/[0.02] pointer-events-none" />
            <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[280px] h-[280px] bg-yellow-400/[0.03] rounded-full blur-[90px] pointer-events-none" />
            <div className="absolute bottom-1/4 left-1/3 w-[200px] h-[200px] bg-neutral-100/[0.02] rounded-full blur-[80px] pointer-events-none" />

            {/* HEADER AREA: Fixed and high density */}
            <header className="w-full flex flex-col items-center justify-center pt-3 sm:pt-6 pb-1 sm:pb-2 z-10 shrink-0">
                <h1 className="text-3xl sm:text-4xl font-caveat font-bold text-[#faf8f5] tracking-wider leading-none select-none drop-shadow-md">
                    Past Forward
                </h1>
                {isLoading ? (
                    <p className="font-mono text-[9px] text-[#ff9f1c] mt-1 tracking-[0.25em] uppercase animate-pulse">
                        DEVELOPING PORTRAITS LIVE
                    </p>
                ) : (
                    <p className="font-mono text-[9px] text-neutral-500 mt-1 tracking-[0.25em] uppercase">
                        PORTRAITS THROUGH THE DECADES
                    </p>
                )}
            </header>

            {/* CENTER STAGE: Where images are presented. Fluid height restricts any overflows */}
            <section className={cn(
                "flex-1 w-full mx-auto flex flex-col justify-center items-center overflow-hidden px-4 z-10 min-h-0 relative transition-all duration-300",
                (appState === 'results-shown' && !isMobile) ? "max-w-5xl" : "max-w-lg"
            )}>
                
                {appState === 'idle' && (
                    <div className="flex flex-col items-center justify-center w-full h-full py-4 text-center">
                        <label 
                            htmlFor="file-upload" 
                            className="flex flex-col items-center justify-center w-full cursor-pointer group transform hover:scale-[1.02] active:scale-[0.98] transition-transform duration-300"
                        >
                            <PolaroidCard 
                                caption="Choose Photo"
                                status="done"
                                size="normal"
                                isMobile={isMobile}
                            />
                        </label>
                        <input 
                            id="file-upload" 
                            type="file" 
                            className="hidden" 
                            accept="image/png, image/jpeg, image/webp" 
                            onChange={handleImageUpload} 
                        />
                    </div>
                )}

                {appState === 'image-uploaded' && uploadedImage && (
                    <div className="flex flex-col items-center justify-center w-full h-full py-4 text-center">
                        <PolaroidCard 
                            imageUrl={uploadedImage} 
                            caption="Original Portrait" 
                            status="done"
                            size="normal"
                            isMobile={isMobile}
                        />
                    </div>
                )}

                {appState === 'results-shown' && (
                    <div className="w-full h-full flex flex-col justify-center items-center py-2">
                        {isMobile ? (
                            mobileViewMode === 'slider' ? (
                                /* Swipable Deck: Elegant Drag Gestures */
                                <div className="w-full flex flex-col items-center justify-center">
                                    <motion.div
                                        key={activeDecadeIndex}
                                        drag="x"
                                        dragConstraints={{ left: 0, right: 0 }}
                                        dragElastic={0.6}
                                        onDragEnd={(e, info) => {
                                            const shiftX = info.offset.x;
                                            const selectVel = info.velocity.x;
                                            if (shiftX < -60 || selectVel < -300) {
                                                setActiveDecadeIndex(prev => (prev < DECADES.length - 1 ? prev + 1 : 0));
                                            } else if (shiftX > 60 || selectVel > 300) {
                                                setActiveDecadeIndex(prev => (prev > 0 ? prev - 1 : DECADES.length - 1));
                                            }
                                        }}
                                        initial={{ opacity: 0.8, x: 20 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        className="w-full flex justify-center cursor-grab active:cursor-grabbing touch-none"
                                    >
                                        <PolaroidCard
                                            caption={DECADES[activeDecadeIndex]}
                                            status={generatedImages[DECADES[activeDecadeIndex]]?.status || 'pending'}
                                            imageUrl={generatedImages[DECADES[activeDecadeIndex]]?.url}
                                            error={generatedImages[DECADES[activeDecadeIndex]]?.error}
                                            placeholderUrl={uploadedImage || undefined}
                                            onShake={handleRegenerateDecade}
                                            onDownload={handleDownloadIndividualImage}
                                            isMobile={isMobile}
                                        />
                                    </motion.div>

                                    <div className="flex justify-between items-center w-full max-w-[270px] mt-4 z-10 relative">
                                        <button
                                            onClick={() => setActiveDecadeIndex(prev => (prev > 0 ? prev - 1 : DECADES.length - 1))}
                                            className="p-1 px-3 text-[11px] font-mono text-neutral-400 bg-neutral-900 border border-neutral-805 rounded-md active:scale-95 transition-all hover:bg-neutral-850 hover:text-white"
                                        >
                                            ◀ PREV
                                        </button>
                                        <span className="font-mono text-xs text-yellow-405 tracking-wider font-bold text-[#ff9f1c]">
                                            {DECADES[activeDecadeIndex]}
                                        </span>
                                        <button
                                            onClick={() => setActiveDecadeIndex(prev => (prev < DECADES.length - 1 ? prev + 1 : 0))}
                                            className="p-1 px-3 text-[11px] font-mono text-neutral-400 bg-neutral-900 border border-neutral-805 rounded-md active:scale-95 transition-all hover:bg-neutral-850 hover:text-white"
                                        >
                                            NEXT ▶
                                        </button>
                                    </div>

                                    {/* Pagination indicator bullet dots */}
                                    <div className="flex gap-2.5 mt-3">
                                        {DECADES.map((dec, i) => (
                                            <button
                                                key={dec}
                                                onClick={() => setActiveDecadeIndex(i)}
                                                className={cn(
                                                    "h-1.5 rounded-full transition-all duration-300",
                                                    i === activeDecadeIndex 
                                                        ? "bg-yellow-400 w-4" 
                                                        : "bg-white/20 w-1.5"
                                                )}
                                                aria-label={`Go to ${dec}`}
                                            />
                                        ))}
                                    </div>
                                </div>
                            ) : (
                                /* Bento Album Grid View (Fits within screen size comfortably) */
                                <div className="grid grid-cols-3 gap-2 w-full px-1 max-w-sm justify-items-center">
                                    {DECADES.map((decade, idx) => (
                                        <motion.div
                                            key={decade}
                                            onClick={() => {
                                                setActiveDecadeIndex(idx);
                                                setMobileViewMode('slider');
                                            }}
                                            className="w-full max-w-[105px] cursor-pointer"
                                            whileTap={{ scale: 0.95 }}
                                        >
                                            <PolaroidCard
                                                caption={decade}
                                                status={generatedImages[decade]?.status || 'pending'}
                                                imageUrl={generatedImages[decade]?.url}
                                                error={generatedImages[decade]?.error}
                                                placeholderUrl={uploadedImage || undefined}
                                                size="sm"
                                                isMobile={isMobile}
                                            />
                                        </motion.div>
                                    ))}
                                </div>
                            )
                        ) : (
                            /* Desktop scattered table grid */
                            <div ref={dragAreaRef} className="relative w-full max-w-5xl h-[420px] sm:h-[480px]">
                                {DECADES.map((decade, index) => {
                                    const { top, left, rotate } = POSITIONS[index];
                                    return (
                                        <motion.div
                                            key={decade}
                                            className="absolute cursor-grab active:cursor-grabbing"
                                            style={{ top, left }}
                                            initial={{ opacity: 0, scale: 0.5, y: 100, rotate: 0 }}
                                            animate={{ 
                                                opacity: 1, 
                                                scale: 1, 
                                                y: 0,
                                                rotate: `${rotate}deg`,
                                            }}
                                            transition={{ type: 'spring', stiffness: 90, damping: 18, delay: index * 0.1 }}
                                        >
                                            <PolaroidCard 
                                                dragConstraintsRef={dragAreaRef}
                                                caption={decade}
                                                status={generatedImages[decade]?.status || 'pending'}
                                                imageUrl={generatedImages[decade]?.url}
                                                error={generatedImages[decade]?.error}
                                                placeholderUrl={uploadedImage || undefined}
                                                onShake={handleRegenerateDecade}
                                                onDownload={handleDownloadIndividualImage}
                                                isMobile={isMobile}
                                            />
                                        </motion.div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                )}
            </section>

            {/* BOTTOM SHELF ACTION GLASS PANEL */}
            <footer className="w-full px-4 pb-4 sm:pb-8 pt-1 z-10 shrink-0">
                <div className="w-full max-w-sm mx-auto bg-neutral-900/80 backdrop-blur-md border border-neutral-800/60 rounded-2xl p-3 sm:p-4 shadow-xl flex flex-col items-center">
                    
                    {appState === 'idle' && (
                        <div className="w-full text-center">
                            <button
                                onClick={() => document.getElementById('file-upload')?.click()}
                                className="w-full py-3 px-5 bg-gradient-to-r from-yellow-500 to-yellow-400 text-black hover:from-yellow-400 hover:to-yellow-300 active:scale-[0.98] font-mono text-xs font-bold uppercase rounded-xl tracking-widest transition-all shadow-[0_4px_12px_rgba(234,179,8,0.25)] flex items-center justify-center gap-2"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                </svg>
                                CHOOSE PORTRAIT PHOTO
                            </button>
                        </div>
                    )}

                    {appState === 'image-uploaded' && (
                        <div className="w-full flex flex-col gap-2">
                            <button
                                onClick={handleGenerateClick}
                                className="w-full py-3 px-5 bg-gradient-to-r from-yellow-400 to-amber-500 text-black hover:from-yellow-300 hover:to-amber-400 active:scale-[0.98] font-mono text-xs font-bold uppercase rounded-xl tracking-widest transition-all shadow-[0_4px_12px_rgba(234,179,8,0.3)] flex items-center justify-center gap-2"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                                </svg>
                                REIMAGINE MY PORTRAIT
                            </button>
                            <button
                                onClick={handleReset}
                                className="w-full py-2 bg-neutral-950 border border-neutral-800 text-neutral-400 hover:text-white hover:border-neutral-700 active:scale-[0.97] font-mono text-[10px] uppercase rounded-lg tracking-wider transition-all"
                            >
                                CHOOSE DIFFERENT PHOTO
                            </button>
                        </div>
                    )}

                    {appState === 'results-shown' && (
                        <div className="w-full flex flex-col gap-2.5">
                            {isLoading ? (
                                <div className="w-full bg-[#141211]/90 border border-neutral-900 rounded-xl p-3 sm:p-4 flex flex-col gap-2.5 text-center shadow-lg relative overflow-hidden animate-pulse">
                                    <div className="absolute top-0 inset-x-0 h-0.5 bg-gradient-to-r from-yellow-400 via-amber-500 to-yellow-600" />
                                    <div className="flex justify-between items-center text-[10px] font-mono uppercase tracking-[0.15em] text-[#ff9f1c] font-bold">
                                        <span>FILM DEVELOPER ACTIVE</span>
                                        <span>{completedCount} / {DECADES.length} STYLES</span>
                                    </div>
                                    
                                    {/* Progress Track */}
                                    <div className="w-full h-1 bg-neutral-900 rounded-full overflow-hidden">
                                        <div 
                                            className="h-full bg-gradient-to-r from-amber-500 to-yellow-400 transition-all duration-500" 
                                            style={{ width: `${(completedCount / DECADES.length) * 100}%` }}
                                        />
                                    </div>
                                    <p className="text-[10.5px] text-neutral-400 font-sans leading-relaxed">
                                        Developing your portraits. Feel free to <strong className="text-yellow-400/90 font-medium">swipe/drag the cards</strong> to preview each decade's chemical treatment!
                                    </p>
                                </div>
                            ) : (
                                <React.Fragment>
                                    {/* Segment selector toggle for Mobile Mode exclusively */}
                                    {isMobile && (
                                        <div className="flex bg-black border border-neutral-800 rounded-lg p-0.5 w-full">
                                            <button
                                                onClick={() => setMobileViewMode('slider')}
                                                className={cn(
                                                    "flex-1 py-1.5 text-[10px] font-mono rounded-md transition-all flex items-center justify-center gap-1.5",
                                                    mobileViewMode === 'slider' 
                                                        ? "bg-neutral-905 text-yellow-400 font-bold border border-neutral-800 shadow-sm" 
                                                        : "text-neutral-500 hover:text-neutral-300"
                                                )}
                                            >
                                                SINGLE CARD
                                            </button>
                                            <button
                                                onClick={() => setMobileViewMode('grid')}
                                                className={cn(
                                                    "flex-1 py-1.5 text-[10px] font-mono rounded-md transition-all flex items-center justify-center gap-1.5",
                                                    mobileViewMode === 'grid' 
                                                        ? "bg-neutral-905 text-yellow-400 font-bold border border-neutral-800 shadow-sm" 
                                                        : "text-neutral-500 hover:text-neutral-300"
                                                )}
                                            >
                                                ALBUM BOOKLET
                                            </button>
                                        </div>
                                    )}

                                    {/* Download collage and Start over buttons */}
                                    <div className="flex gap-2 w-full animate-fadeIn">
                                        <button 
                                            onClick={handleDownloadAlbum} 
                                            disabled={isDownloading} 
                                            className="flex-1 py-3 px-2 bg-gradient-to-r from-yellow-400 to-amber-500 text-black hover:from-yellow-300 hover:to-amber-400 active:scale-[0.98] font-mono text-[10.5px] font-bold uppercase rounded-xl tracking-widest transition-all disabled:opacity-50 select-none shadow-[0_3px_10px_rgba(234,179,8,0.2)]"
                                        >
                                            {isDownloading ? 'CREATING...' : 'COLLAGE ALBUM'}
                                        </button>
                                        <button 
                                            onClick={handleReset} 
                                            className="flex-1 py-3 px-2 bg-neutral-950 border border-neutral-800/85 text-neutral-400 hover:text-white hover:border-neutral-700 active:scale-[0.98] font-mono text-[10.5px] font-medium uppercase rounded-xl tracking-wider transition-all select-none"
                                        >
                                            START OVER
                                        </button>
                                    </div>
                                </React.Fragment>
                            )}
                        </div>
                    )}
                </div>
            </footer>

            {/* ERROR BANNER: Graceful absolute center feedback */}
            {errorMessage && (
                <div className="absolute top-24 left-4 right-4 bg-red-950/90 border border-red-500/40 p-3 rounded-lg text-center shadow-2xl backdrop-blur-xl z-50 max-w-sm mx-auto flex items-center justify-between">
                    <span className="font-mono text-[11px] text-red-200">{errorMessage}</span>
                    <button onClick={() => setErrorMessage(null)} className="text-red-400 text-xs px-2 select-none hover:text-red-200">✕</button>
                </div>
            )}
        </main>
    );
}

export default App;
