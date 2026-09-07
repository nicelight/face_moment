/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import React, { useState, useEffect, useRef } from 'react';
import { DraggableCardContainer, DraggableCardBody } from './ui/draggable-card';
import { cn } from '../lib/utils';
import type { PanInfo } from 'framer-motion';
import { RotateCw, Download, AlertCircle, Clock, Plus } from 'lucide-react';

type ImageStatus = 'pending' | 'done' | 'error';

interface PolaroidCardProps {
    imageUrl?: string;
    caption: string;
    status: ImageStatus;
    error?: string;
    dragConstraintsRef?: React.RefObject<HTMLElement>;
    onShake?: (caption: string) => void;
    onDownload?: (caption: string) => void;
    isMobile?: boolean;
    size?: 'normal' | 'sm' | 'lg';
    placeholderUrl?: string;
}

const LoadingSpinner = ({ caption, placeholderUrl }: { caption: string; placeholderUrl?: string }) => (
    <div className="relative w-full h-full bg-[#181615] overflow-hidden flex flex-col items-center justify-center">
        {placeholderUrl ? (
            <div className="absolute inset-0 w-full h-full">
                <img 
                    src={placeholderUrl} 
                    alt="Developing silhouette" 
                    className="w-full h-full object-cover opacity-20 filter sepia(1.2) blur-[3px]"
                    referrerPolicy="no-referrer"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/40 to-[#181615]/30" />
            </div>
        ) : null}
        
        {/* Animated chemical scanline / radar loop */}
        <div className="relative w-12 h-12 mb-3 z-10">
            <div className="absolute inset-0 rounded-full border border-[#ff9f1c]/15 animate-ping" />
            <div className="absolute inset-0 rounded-full border-2 border-t-[#ff9f1c] border-r-[#ff9f1c]/20 animate-spin" />
            <div className="absolute inset-2.5 rounded-full bg-[#ff9f1c]/5 flex items-center justify-center">
                <Clock className="h-4 w-4 animate-pulse text-[#ff9f1c]" />
            </div>
        </div>
        <span className="font-mono text-[9px] tracking-[0.2em] text-[#ff9f1c] font-bold uppercase animate-pulse z-10">Developing</span>
        <span className="font-mono text-[8px] text-neutral-400 mt-0.5 tracking-wider uppercase z-10 max-w-[145px] truncate">{caption}</span>
    </div>
);

const ErrorDisplay = ({ error, onRetry }: { error?: string; onRetry?: () => void }) => (
    <div className="flex flex-col items-center justify-center h-full bg-neutral-950 p-4 border border-red-500/10">
        <div className="bg-red-500/10 p-2.5 rounded-full mb-2">
            <AlertCircle className="h-6 w-6 text-red-400" />
        </div>
        <p className="font-permanent-marker text-xs text-red-500 tracking-wider text-center max-w-[200px] line-clamp-2 leading-tight">
            DEVELOPMENT FAILED
        </p>
        <p className="text-[9px] font-mono text-neutral-500 text-center mt-1 max-w-[180px] break-words line-clamp-3">
            {error || 'Request TIMEOUT or Rate Limit exceeded.'}
        </p>
        {onRetry && (
            <button 
                onClick={(e) => {
                    e.stopPropagation();
                    onRetry();
                }}
                className="mt-3 px-3 py-1 bg-red-500/20 hover:bg-red-500/30 active:scale-95 border border-red-500/40 text-[10px] font-mono text-red-300 rounded transition-all shadow-sm"
            >
                RE-DEVELOP
            </button>
        )}
    </div>
);

const Placeholder = () => (
    <div className="flex flex-col items-center justify-center h-full text-neutral-400 group-hover:text-yellow-400 bg-neutral-900 border-2 border-dashed border-neutral-800 transition-colors duration-500">
        <div className="w-12 h-12 rounded-full border border-neutral-800 flex items-center justify-center mb-3 group-hover:border-yellow-400/30 transition-colors">
            <Plus className="h-5 w-5" />
        </div>
        <span className="font-permanent-marker text-sm tracking-widest text-neutral-500 group-hover:text-yellow-400/80 transition-colors">UPLOAD PORTRAIT</span>
        <span className="font-mono text-[9px] text-neutral-600 mt-1 uppercase">TAP TO SELECT</span>
    </div>
);

const PolaroidCard: React.FC<PolaroidCardProps> = ({ imageUrl, caption, status, error, dragConstraintsRef, onShake, onDownload, isMobile, size = 'normal', placeholderUrl }) => {
    const [isDeveloped, setIsDeveloped] = useState(false);
    const [isImageLoaded, setIsImageLoaded] = useState(false);
    const lastShakeTime = useRef(0);
    const lastVelocity = useRef({ x: 0, y: 0 });
    const imgRef = useRef<HTMLImageElement | null>(null);

    // Callback ref to handle cached images loading before React binds onLoad events
    const imageRefCallback = (node: HTMLImageElement | null) => {
        if (node) {
            imgRef.current = node;
            if (node.complete) {
                setIsImageLoaded(true);
            }
        } else {
            imgRef.current = null;
        }
    };

    // Reset states when the image URL changes or status goes to pending.
    useEffect(() => {
        if (status === 'pending') {
            setIsDeveloped(false);
            setIsImageLoaded(false);
        }
        if (status === 'done' && imageUrl) {
            setIsDeveloped(false);
            if (imgRef.current && imgRef.current.complete) {
                setIsImageLoaded(true);
            } else {
                setIsImageLoaded(false);
            }
        }
    }, [imageUrl, status]);

    // When the image is loaded, start the developing animation.
    useEffect(() => {
        if (isImageLoaded) {
            const timer = setTimeout(() => {
                setIsDeveloped(true);
            }, 300); // Short delay before chemical treatment fades out
            return () => clearTimeout(timer);
        }
    }, [isImageLoaded]);

    const handleDragStart = () => {
        lastVelocity.current = { x: 0, y: 0 };
    };

    const handleDrag = (event: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
        if (!onShake || isMobile) return;

        const velocityThreshold = 1500;
        const shakeCooldown = 2000;

        const { x, y } = info.velocity;
        const { x: prevX, y: prevY } = lastVelocity.current;
        const now = Date.now();

        const magnitude = Math.sqrt(x * x + y * y);
        const dotProduct = (x * prevX) + (y * prevY);

        if (magnitude > velocityThreshold && dotProduct < 0 && (now - lastShakeTime.current > shakeCooldown)) {
            lastShakeTime.current = now;
            onShake(caption);
        }

        lastVelocity.current = { x, y };
    };

    const isSmall = size === 'sm';
    const isLarge = size === 'lg';

    const cardInnerContent = (
        <React.Fragment>
            {/* Aspect Container with slightly indented inner bounds */}
            <div className="w-full aspect-square bg-[#121110] shadow-inner relative overflow-hidden group">
                {status === 'pending' && <LoadingSpinner caption={caption} placeholderUrl={placeholderUrl} />}
                {status === 'error' && <ErrorDisplay error={error} onRetry={onShake ? () => onShake(caption) : undefined} />}
                {status === 'done' && imageUrl && (
                    <React.Fragment>
                        {/* Overlay Controls */}
                        <div className={cn(
                            "absolute top-2 right-2 z-20 flex flex-col gap-1.5 transition-all duration-300",
                            (!isMobile && !isSmall) && "opacity-0 group-hover:opacity-100 scale-95 group-hover:scale-100",
                        )}>
                            {!isSmall && onDownload && (
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onDownload(caption);
                                    }}
                                    className="p-1.5 bg-black/60 backdrop-blur-md border border-white/10 rounded-full text-white hover:bg-yellow-400 hover:text-black transition-colors focus:outline-none focus:ring-1 focus:ring-yellow-400"
                                    aria-label={`Download image for ${caption}`}
                                    title="Download Portrait"
                                >
                                    <Download className="h-4 w-4" />
                                </button>
                            )}
                            {!isSmall && onShake && (
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onShake(caption);
                                    }}
                                    className="p-1.5 bg-black/60 backdrop-blur-md border border-white/10 rounded-full text-white hover:bg-yellow-400 hover:text-black transition-colors focus:outline-none focus:ring-1 focus:ring-yellow-400"
                                    aria-label={`Regenerate image for ${caption}`}
                                    title="Regenerate Portrait"
                                >
                                    <RotateCw className="h-4 w-4" />
                                </button>
                            )}
                        </div>

                        {/* Immersive Developing chemical layer */}
                        <div
                            className={cn(
                                "absolute inset-0 z-10 transition-all duration-[4000ms] pointer-events-none",
                                isDeveloped 
                                    ? "opacity-0 bg-transparent" 
                                    : "opacity-100 bg-gradient-to-tr from-[#2b1810] via-[#483724] to-[#1a110d] mix-blend-color-burn"
                            )}
                            aria-hidden="true"
                        />
                        <div
                            className={cn(
                                "absolute inset-0 z-10 transition-opacity duration-[3500ms] pointer-events-none bg-[#3a322c]",
                                isDeveloped ? "opacity-0" : "opacity-95"
                            )}
                            aria-hidden="true"
                        />
                        
                        {/* Real Image Render */}
                        <img
                            ref={imageRefCallback}
                            key={imageUrl}
                            src={imageUrl}
                            alt={caption}
                            onLoad={() => setIsImageLoaded(true)}
                            className={cn(
                                "w-full h-full object-cover select-none pointer-events-none transition-all duration-[4500ms] ease-out",
                                isDeveloped 
                                    ? "opacity-100 filter-none brightness-100 contrast-100" 
                                    : "opacity-30 filter sepia(1.2) contrast(0.6) brightness(1.2) blur-[0.5px]"
                            )}
                            style={{ opacity: isImageLoaded ? undefined : 0 }}
                            referrerPolicy="no-referrer"
                        />
                        {/* Subtle gloss overlay to mimic real photopaper */}
                        <div className="absolute inset-0 bg-gradient-to-tr from-transparent via-white/[0.04] to-white/[0.08] pointer-events-none z-15" />
                    </React.Fragment>
                )}
                {status === 'done' && !imageUrl && <Placeholder />}
            </div>
            
            {/* Handwritten Label */}
            <div className={cn(
                "w-full flex-grow flex items-center justify-center text-center",
                isSmall 
                    ? "px-1 pb-1" 
                    : isLarge 
                        ? "px-4 pb-3" 
                        : "px-3 pb-2"
            )}>
                <p className={cn(
                    "font-caveat truncate px-1 select-none tracking-wide font-bold text-slate-800 rotate-[-1deg] leading-none",
                    isSmall 
                        ? "text-[11px] sm:text-xs" 
                        : isLarge
                            ? "text-[26px] xs:text-[30px] sm:text-[34px]"
                            : "text-2xl sm:text-3xl",
                    status === 'done' && imageUrl ? 'text-[#24211e]' : 'text-neutral-500'
                )}>
                    {caption}
                </p>
            </div>
        </React.Fragment>
    );

    // Responsive Native-Looking Mobile or Miniature Sizing
    if (isMobile || isSmall) {
        return (
            <div className={cn(
                "bg-[#fdfbf7] flex flex-col items-center justify-start rounded text-neutral-900 border border-black/5 select-none overflow-hidden",
                isSmall 
                    ? "w-full aspect-[5/6] p-1.5 pb-0 shadow-md" 
                    : isLarge
                        ? "w-full max-w-[380px] xs:max-w-[420px] sm:max-w-[470px] aspect-[5/6] p-4 pb-0 shadow-yellow-500/10 shadow-[0px_15px_45px_rgba(0,0,0,0.5)]"
                        : "h-[45dvh] max-h-[340px] min-h-[260px] aspect-[5/6] p-3 pb-0 shadow-yellow-500/5 shadow-[0px_10px_35px_rgba(0,0,0,0.4)]"
            )}>
                {cardInnerContent}
            </div>
        );
    }

    // Classic Draggable Light-table Styling for Desktop
    return (
        <DraggableCardContainer>
            <DraggableCardBody 
                className={cn(
                    "bg-[#fdfbf7] flex flex-col items-center justify-start aspect-[5/6] shadow-2xl border border-black/5 rounded",
                    isLarge 
                        ? "w-[440px] p-6 pb-0" 
                        : "w-80 p-4 pb-0"
                )}
                dragConstraintsRef={dragConstraintsRef}
                onDragStart={handleDragStart}
                onDrag={handleDrag}
            >
                {cardInnerContent}
            </DraggableCardBody>
        </DraggableCardContainer>
    );
};

export default PolaroidCard;
