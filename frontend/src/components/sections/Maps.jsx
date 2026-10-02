import React, { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

const Maps = () => {
  const sectionRef = useRef(null);
  const videoRef = useRef(null);

  useEffect(() => {
    const section = sectionRef.current;
    const video = videoRef.current;
    if (!section || !video) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && entry.intersectionRatio >= 0.2) {
          video.play().catch(() => {});
        } else {
          video.pause();
        }
      },
      { threshold: [0, 0.2] },
    );

    observer.observe(section);
    return () => observer.disconnect();
  }, []);

  return (
    <>
    <section
      id="maps"
      ref={sectionRef}
      className="relative overflow-hidden bg-black py-16 sm:py-20 lg:py-24"
    >
      <div className="relative z-10 mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 25 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="text-left"
        >
          <div className="inline-block">
            <h2 className="font-ledger text-4xl font-semibold tracking-tight text-white sm:text-5xl md:text-6xl">
              map of{" "}
              <span className="bg-gradient-to-r from-purple-400 via-pink-500 to-purple-400 bg-clip-text text-transparent">
                road defects
              </span>
            </h2>
            <div className="mt-3 flex w-full items-center">
              <div className="h-px flex-1 bg-white/40" />
              <div className="ml-1.5 h-1.5 w-1.5 rounded-full bg-white/70" />
            </div>
          </div>

          <p className="mt-8 max-w-5xl font-ledger text-base leading-relaxed text-gray-300 sm:text-lg lg:text-xl">
            Once your drive is complete, the road defects you drove over will
            be put on the map anonymously.
          </p>
        </motion.div>

        <div className="mt-10 flex justify-center">
          <Link
            to="/map"
            className="inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 font-ledger text-sm font-semibold text-black transition-colors hover:bg-gray-200 sm:text-base"
          >
            Go to maps
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>

        <div className="mx-auto mt-12 w-full max-w-5xl rounded-2xl bg-white p-1 shadow-[0_24px_64px_rgba(0,0,0,0.4)] sm:mt-14 sm:p-1.5">
          <video
            ref={videoRef}
            className="aspect-[1918/906] w-full rounded-xl bg-white object-cover"
            src="/map_recording.mp4"
            muted
            loop
            playsInline
            preload="metadata"
            aria-label="Preview of the road defects map"
          />
        </div>

      </div>
    </section>
    <section className="bg-black pb-16 sm:pb-20 lg:pb-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto w-full max-w-5xl border-t border-white/70 pt-8 sm:pt-10">
          <h2 className="text-center font-ledger text-3xl font-semibold text-white sm:text-4xl">
            What to{" "}
            <span className="bg-gradient-to-r from-purple-400 via-pink-500 to-purple-400 bg-clip-text text-transparent">
              explore
            </span>{" "}
            next:
          </h2>
          <ul className="mt-4 list-disc space-y-12 pl-6 font-ledger text-base text-gray-300 sm:text-lg">
            <li>
              <Link className="underline underline-offset-4 transition-colors hover:text-white" to="/vmn">
                Learn more about the vehnicate Merchant Network.
              </Link>
            </li>
            <li>
              <Link className="underline underline-offset-4 transition-colors hover:text-white" to="/ellar">
                Learn more about the working of the Ellar.
              </Link>
            </li>
          </ul>
        </div>
      </div>
    </section>
    </>
  );
};

export default Maps;
