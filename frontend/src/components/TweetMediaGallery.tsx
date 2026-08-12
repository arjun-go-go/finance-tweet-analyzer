"use client";

import { useEffect, useState } from "react";
import { fetchTweetMediaBlob } from "@/lib/api";

export interface TweetMediaItem {
  id: string;
  width?: number | null;
  height?: number | null;
  content_type?: string | null;
}

interface LoadedMedia extends TweetMediaItem {
  url: string;
}

export default function TweetMediaGallery({
  tweetId,
  media,
}: {
  tweetId: string;
  media: TweetMediaItem[];
}) {
  const [loaded, setLoaded] = useState<LoadedMedia[]>([]);
  const [loading, setLoading] = useState(media.length > 0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    const objectUrls: string[] = [];

    setLoaded([]);
    setFailed(false);
    setLoading(media.length > 0);

    if (!media.length) {
      return () => undefined;
    }

    void Promise.all(
      media.map(async (item) => {
        try {
          const blob = await fetchTweetMediaBlob(tweetId, item.id);
          const url = URL.createObjectURL(blob);
          objectUrls.push(url);
          return { ...item, url };
        } catch {
          return null;
        }
      }),
    ).then((results) => {
      if (!active) return;
      const successful = results.filter((item): item is LoadedMedia => item !== null);
      setLoaded(successful);
      setFailed(successful.length === 0);
      setLoading(false);
    });

    return () => {
      active = false;
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [tweetId, media]);

  if (!media.length) return null;

  if (loading) {
    return (
      <div className={`mt-3 grid gap-2 ${media.length === 1 ? "max-w-2xl grid-cols-1" : "grid-cols-2"}`} aria-label="推文图片加载中">
        {media.map((item) => (
          <div key={item.id} className="aspect-[4/3] animate-pulse rounded-xl bg-slate-100" />
        ))}
      </div>
    );
  }

  if (failed) {
    return <p className="mt-3 text-xs text-slate-400">图片暂时无法加载</p>;
  }

  const isSingle = loaded.length === 1;
  return (
    <div className={`mt-3 grid gap-2 overflow-hidden rounded-2xl ${isSingle ? "max-w-2xl grid-cols-1" : "grid-cols-2"}`}>
      {loaded.map((item, index) => {
        const dimensions = item.width && item.height ? `${item.width} × ${item.height}` : "查看原图";
        return (
          <a
            key={item.id}
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className={`group relative flex min-h-40 items-center justify-center overflow-hidden rounded-xl border border-slate-200 bg-slate-950 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:ring-offset-2 ${isSingle ? "max-h-[520px]" : "aspect-[4/3]"}`}
            aria-label={`查看第 ${index + 1} 张推文图片原图`}
          >
            {/* Blob URLs require a regular img element; Next Image cannot optimize them. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={item.url}
              alt={`推文图片 ${index + 1}`}
              className={`w-full object-contain transition duration-200 group-hover:scale-[1.01] ${isSingle ? "max-h-[520px]" : "h-full"}`}
            />
            <span className="absolute bottom-2 right-2 rounded-md bg-slate-950/75 px-2 py-1 text-[10px] font-medium text-white opacity-0 backdrop-blur-sm transition group-hover:opacity-100 group-focus:opacity-100">
              {dimensions}
            </span>
          </a>
        );
      })}
    </div>
  );
}
