import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Link } from "react-router-dom";

const MotionLink = motion(Link);

// ============================================================
// DESCRIPTION SEGMENTS
// ============================================================
const descriptionSegments = [
  {
    type: "text",
    content: "Every road-defect you drive over with our ",
  },
  {
    type: "appLink",
    content: "app",
  },
  {
    type: "text",
    content: " will be put on the ",
  },
  {
    type: "link",
    content: "map",
  },
  {
    type: "text",
    content: " and will be used to save lives.",
  },
  {
    type: "break",
  },
  {
    type: "text",
    content:
      "As a token of appreciation, the system rewards you with our virtual token - ",
  },
  {
    type: "gradient",
    content: "the Ellar",
  },
  {
    type: "text",
    content: ".",
  },
];

const TOTAL_TYPED_CHARS = descriptionSegments.reduce(
  (sum, seg) =>
    sum + (seg.type === "break" ? 0 : seg.content.length),
  0
);

const Hero = () => {
  const [currentWordIndex, setCurrentWordIndex] = useState(0);
  const [typedCount, setTypedCount] = useState(0);

  const rotatingWords = ["pothole", "speedbreaker"];

  // ============================================================
  // ROTATING POTHOLE / SPEEDBREAKER TEXT
  // ============================================================
  useEffect(() => {
    const wordInterval = setInterval(() => {
      setCurrentWordIndex(
        (prev) => (prev + 1) % rotatingWords.length
      );
    }, 2500);

    return () => clearInterval(wordInterval);
  }, []);

  // ============================================================
  // TYPEWRITER EFFECT
  // ============================================================
  useEffect(() => {
    let charIndex = 0;
    let startId;
    let tickId;

    const tick = () => {
      charIndex += 1;
      setTypedCount(charIndex);

      if (charIndex < TOTAL_TYPED_CHARS) {
        tickId = setTimeout(tick, 25);
      }
    };

    // wait for the splash's 0.55s fade-out to finish, then type from char 1
    const start = () => {
      startId = setTimeout(tick, 600);
    };

    if (window.__splashDone) {
      // splash already played (e.g. returning from /map)
      start();
    } else {
      window.addEventListener("splash-complete", start, { once: true });
    }

    return () => {
      clearTimeout(startId);
      clearTimeout(tickId);
      window.removeEventListener("splash-complete", start);
    };
  }, []);

  // ============================================================
  // RENDER DESCRIPTION PROGRESSIVELY
  // ============================================================
  const renderTypedDescription = () => {
    let consumed = 0;
    const output = [];

    for (let i = 0; i < descriptionSegments.length; i++) {
      const seg = descriptionSegments[i];

      // --------------------------------------------------------
      // LINE BREAK
      // --------------------------------------------------------
      if (seg.type === "break") {
        if (consumed <= typedCount) {
          output.push(<br key={i} />);
          continue;
        } else {
          break;
        }
      }

      const remaining = typedCount - consumed;

      if (remaining <= 0) {
        break;
      }

      const visibleText = seg.content.slice(0, remaining);

      // --------------------------------------------------------
      // NORMAL TEXT
      // --------------------------------------------------------
      if (seg.type === "text") {
        output.push(
          <React.Fragment key={i}>
            {visibleText}
          </React.Fragment>
        );
      }

      // --------------------------------------------------------
      // MAP LINK
      // --------------------------------------------------------
      if (seg.type === "link") {
        output.push(
          <Link
            key={i}
            to="/map"
            className="text-purple-400 underline decoration-purple-400/50 hover:text-pink-400 hover:decoration-pink-400/50 transition-colors duration-300 cursor-pointer"
          >
            {visibleText}
          </Link>
        );
      }
      // --------------------------------------------------------
      // APP LINK
      // --------------------------------------------------------
      if (seg.type === "appLink") {
        output.push(
          <a
            key={i}
            href="https://play.google.com/store/apps/details?id=com.vehnway.app&pcampaignid=web_share"
            target="_blank"
            rel="noopener noreferrer"
            className="text-purple-400 underline decoration-purple-400/50 hover:text-pink-400 hover:decoration-pink-400/50 transition-colors duration-300 cursor-pointer"
          >
            {visibleText}
          </a>
        );
      }

      // --------------------------------------------------------
      // ELLAR GRADIENT
      // --------------------------------------------------------
      if (seg.type === "gradient") {
        if (visibleText.length === seg.content.length) {
          output.push(
            <span
              key={i}
              className="bg-gradient-to-r from-purple-400 via-pink-500 to-purple-400 bg-clip-text text-transparent font-semibold"
            >
              {visibleText}
            </span>
          );
        } else {
          output.push(
            <span key={i} className="font-semibold">
              {visibleText}
            </span>
          );
        }
      }

      consumed += seg.content.length;

      if (visibleText.length < seg.content.length) {
        break;
      }
    }

    return output;
  };

  return (
    <section
      id="home"
      className="min-h-screen flex items-start lg:items-center bg-black relative overflow-hidden pt-24 lg:pt-20"
    >
      {/* ========================================================
          BACKGROUND
      ========================================================= */}
      <div className="absolute inset-0">

        {/* Main gradient */}
        <div className="absolute inset-0 bg-gradient-to-b from-vehnicate-purple/5 via-vehnicate-pink/5 to-black" />

        {/* Grid */}
        <div
          className="absolute inset-0 opacity-20"
          style={{
            backgroundImage: `
              linear-gradient(rgba(147, 51, 234, 0.1) 1px, transparent 1px),
              linear-gradient(90deg, rgba(147, 51, 234, 0.1) 1px, transparent 1px),
              linear-gradient(rgba(236, 72, 153, 0.05) 1px, transparent 1px),
              linear-gradient(90deg, rgba(236, 72, 153, 0.05) 1px, transparent 1px)
            `,
            backgroundSize:
              "100px 100px, 100px 100px, 20px 20px, 20px 20px",
          }}
        >
          <motion.div
            animate={{
              backgroundPosition: [
                "0px 0px, 0px 0px, 0px 0px, 0px 0px",
                "100px 100px, 100px 100px, 20px 20px, 20px 20px",
              ],
            }}
            transition={{
              duration: 20,
              repeat: Infinity,
              ease: "linear",
            }}
            className="absolute inset-0"
            style={{
              backgroundImage: `
                linear-gradient(rgba(147, 51, 234, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(147, 51, 234, 0.03) 1px, transparent 1px)
              `,
              backgroundSize: "50px 50px, 50px 50px",
            }}
          />
        </div>

        {/* Radial glow */}
        <div className="absolute top-0 left-0 w-full h-full bg-[radial-gradient(ellipse_at_center,rgba(147,51,234,0.1)_0%,rgba(147,51,234,0.05)_50%,transparent_70%)]" />

        {/* Animated radial background */}
        <motion.div
          animate={{
            background: [
              "radial-gradient(circle at 20% 50%, rgba(147,51,234,0.1) 0%, transparent 40%), linear-gradient(to bottom, transparent 60%, rgba(0,0,0,0.8) 100%)",
              "radial-gradient(circle at 80% 50%, rgba(236,72,153,0.1) 0%, transparent 40%), linear-gradient(to bottom, transparent 60%, rgba(0,0,0,0.8) 100%)",
              "radial-gradient(circle at 40% 70%, rgba(147,51,234,0.1) 0%, transparent 40%), linear-gradient(to bottom, transparent 60%, rgba(0,0,0,0.8) 100%)",
            ],
          }}
          transition={{
            duration: 8,
            repeat: Infinity,
            repeatType: "reverse",
          }}
          className="absolute inset-0"
        />

        {/* Bottom fade */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-black" />
      </div>

      {/* ========================================================
          MAIN CONTENT
      ========================================================= */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10 w-full">

        {/* ======================================================
            TWO COLUMN SECTION
        ======================================================= */}
        <div className="flex flex-col lg:flex-row items-center lg:items-start justify-between gap-2 lg:gap-10">

          {/* ====================================================
              LEFT SIDE
          ===================================================== */}
          <motion.div
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1 }}
            className="space-y-4 sm:space-y-6 lg:space-y-8 max-w-2xl text-center lg:text-left w-full lg:w-auto"
          >

            {/* ==================================================
                ANNOUNCEMENTS
            =================================================== */}
            <div className="flex flex-wrap items-center justify-center lg:justify-start gap-2">

              {/* Maps */}
              <MotionLink
                to="/map"
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2, duration: 0.8 }}
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.97 }}
                className="group inline-flex items-center px-4 py-2 bg-white/[0.035] border border-white/10 rounded-2xl backdrop-blur-sm hover:bg-white/[0.06] hover:border-white/20 transition-all duration-300 cursor-pointer"
              >
                <span className="text-xs sm:text-sm font-medium text-purple-300 underline underline-offset-4 decoration-purple-400/50 group-hover:text-pink-400 group-hover:decoration-pink-400/60 transition-colors duration-300">
                  maps is now live
                </span>

                <span className="mx-2 w-1 h-1 rounded-full bg-white/70 shrink-0" />

                <span className="text-xs sm:text-sm font-medium text-purple-300 underline underline-offset-4 decoration-purple-400/50 group-hover:text-pink-400 group-hover:decoration-pink-400/60 transition-colors duration-300">
                  explore!
                </span>
              </MotionLink>

              {/* Google Play App */}
              <motion.a
                href="https://play.google.com/store/apps/details?id=com.vehnway.app&pcampaignid=web_share"
                target="_blank"
                rel="noopener noreferrer"
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.32, duration: 0.8 }}
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.97 }}
                className="group inline-flex items-center px-4 py-2 bg-white/[0.035] border border-white/10 rounded-2xl backdrop-blur-sm hover:bg-white/[0.06] hover:border-white/20 transition-all duration-300 cursor-pointer"
              >
                <span className="text-xs sm:text-sm font-medium text-purple-300 underline underline-offset-4 decoration-purple-400/50 group-hover:text-pink-400 group-hover:decoration-pink-400/60 transition-colors duration-300">
                  the vehnicate app is on the playstore
                </span>

                <span className="mx-2 w-1 h-1 rounded-full bg-white/70 shrink-0" />

                <span className="text-xs sm:text-sm font-medium text-purple-300 underline underline-offset-4 decoration-purple-400/50 group-hover:text-pink-400 group-hover:decoration-pink-400/60 transition-colors duration-300">
                  drive &amp; earn Ellars!
                </span>
              </motion.a>
            </div>

            {/* ==================================================
                HEADING
            =================================================== */}
            <motion.h1
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                delay: 0.4,
                duration: 0.8,
              }}
              className="font-black leading-tight tracking-tight"
            >

              {/* First line */}
              <div className="font-ledger text-white text-2xl sm:text-3xl md:text-4xl lg:text-5xl xl:text-6xl 2xl:text-7xl">
                get rewarded for every
              </div>

              {/* Rotating word */}
              <div className="relative py-0.5 sm:py-1 overflow-hidden">
                <AnimatePresence mode="wait">
                  <motion.span
                    key={currentWordIndex}
                    initial={{
                      opacity: 0,
                      y: 20,
                      filter: "blur(4px)",
                    }}
                    animate={{
                      opacity: 1,
                      y: 0,
                      filter: "blur(0px)",
                    }}
                    exit={{
                      opacity: 0,
                      y: -20,
                      filter: "blur(4px)",
                    }}
                    transition={{
                      duration: 0.6,
                      ease: [0.25, 0.46, 0.45, 0.94],
                    }}
                    className="font-ledger bg-gradient-to-r from-purple-400 via-pink-500 to-purple-400 bg-clip-text text-transparent inline-block text-3xl sm:text-4xl md:text-5xl lg:text-6xl xl:text-7xl 2xl:text-8xl"
                  >
                    {rotatingWords[currentWordIndex]}
                  </motion.span>
                </AnimatePresence>
              </div>

              {/* Third line */}
              <div className="font-ledger text-white text-2xl sm:text-3xl md:text-4xl lg:text-5xl xl:text-6xl 2xl:text-7xl">
                you drive over...
              </div>
            </motion.h1>
          </motion.div>

          {/* ====================================================
              RIGHT SIDE - IMAGE
          ===================================================== */}
          <div className="w-full lg:w-1/2 flex justify-center items-center relative max-w-md sm:max-w-lg lg:max-w-none -mt-2 lg:mt-0">

            {/* Base Image */}
            <motion.div
              initial={{
                opacity: 0,
                scale: 0.9,
              }}
              animate={{
                opacity: 0.5,
                scale: 1.5,
              }}
              transition={{
                delay: 1.4,
                duration: 1,
                ease: [0.16, 1, 0.3, 1],
              }}
              className="w-full flex justify-center"
            >
              <img
                src="/gggyrate.svg"
                alt="Hero Illustration Background"
                className="max-w-full h-auto w-auto max-h-[34vh] sm:max-h-[42vh] lg:max-h-none object-contain rounded-2xl shadow-lg"
              />
            </motion.div>

            {/* Overlay Image */}
            <motion.div
              initial={{
                opacity: 0,
                scale: 0.8,
              }}
              animate={{
                opacity: 1,
                scale: 1,
              }}
              transition={{
                delay: 1.4,
                duration: 1,
                ease: [0.16, 1, 0.3, 1],
              }}
              className="absolute inset-0 flex justify-center items-center"
            >
              <img
                src="/pothole_speedbreaker_ellar.png"
                alt="Hero Illustration Overlay"
                className="h-4/5 w-auto object-contain lg:h-auto lg:w-full lg:max-w-none"
                onError={(e) => {
                  e.target.onerror = null;
                  e.target.src =
                    "https://placehold.co/400x400/000000/FFFFFF?text=Image+Error";
                }}
              />
            </motion.div>
          </div>
        </div>

        {/* ======================================================
            DESCRIPTION
            CLOSER TO THE COLUMNS + ONE SENTENCE PER LINE
        ======================================================= */}
        <div className="relative z-20 w-full text-left text-base sm:text-lg md:text-xl text-gray-300 leading-relaxed font-ledger mt-2 sm:-mt-4 lg:-mt-14 lg:overflow-x-auto">
          <div className="whitespace-normal lg:whitespace-nowrap">
            {renderTypedDescription()}

            {typedCount < TOTAL_TYPED_CHARS && (
              <span className="inline-block w-[2px] h-[1em] bg-purple-400 ml-0.5 align-middle animate-pulse" />
            )}
          </div>
        </div>

      </div>
    </section>
  );
};

export default Hero;