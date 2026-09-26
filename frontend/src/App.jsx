
import { Routes, Route, useLocation } from "react-router-dom";
import {
  AnimatePresence,
  motion,
  useMotionValue,
  useTransform,
  animate,
} from "framer-motion";
import { useEffect, useState, useRef, useCallback } from "react";

import Lenis from "lenis";
import Home from "./pages/Home";
import WaitlistPage from "./pages/WaitlistPage";
import MapPage from "./pages/MapPage";
import Ellar from "./pages/Ellar";
import "./styles/globals.css";
import { Analytics } from "@vercel/analytics/react";

const TIMES_FONT = {
  fontFamily: '"Times New Roman", Times, serif',
};

function SplashScreen({ onComplete }) {
  const [phase, setPhase] = useState("full");
  const [target, setTarget] = useState(null);

  const splashWordRef = useRef(null);

  /*
   * ============================================================
   * MEASURE EXACT DESTINATION
   * ============================================================
   *
   * This is the same center-to-center calculation that gave us
   * the correct endpoint before.
   */

  useEffect(() => {
    if (phase !== "merged") return;

    const measureTarget = () => {
      const headerWordmark =
        document.getElementById("header-wordmark");

      const splashWordmark =
        splashWordRef.current;

      if (!headerWordmark || !splashWordmark) return;

      const headerRect =
        headerWordmark.getBoundingClientRect();

      const splashRect =
        splashWordmark.getBoundingClientRect();

      const headerCenterX =
        headerRect.left + headerRect.width / 2;

      const headerCenterY =
        headerRect.top + headerRect.height / 2;

      const splashCenterX =
        splashRect.left + splashRect.width / 2;

      const splashCenterY =
        splashRect.top + splashRect.height / 2;

      setTarget({
        x: headerCenterX - splashCenterX,
        y: headerCenterY - splashCenterY,
      });
    };

    requestAnimationFrame(() => {
      requestAnimationFrame(measureTarget);
    });

    window.addEventListener("resize", measureTarget);

    return () => {
      window.removeEventListener("resize", measureTarget);
    };
  }, [phase]);

  /*
   * ============================================================
   * TIMELINE
   * ============================================================
   *
   * 0ms
   *     vehicles + communicate
   *
   * 1000ms
   *     transformation begins
   *
   * 2200ms
   *     clean vehnicate
   *
   * 2200 → 3200ms
   *     1 SECOND HOLD
   *
   * 3200ms
   *     curved flight begins
   *
   * 4450ms
   *     flight finishes
   *
   * 5000ms
   *     splash fades away
   */

  useEffect(() => {
    const transformTimer = setTimeout(() => {
      setPhase("transform");
    }, 1000);

    const mergeTimer = setTimeout(() => {
      setPhase("merged");
    }, 2200);

    const moveTimer = setTimeout(() => {
      setPhase("move");
    }, 3200);

    const completeTimer = setTimeout(() => {
      onComplete();
    }, 5000);

    return () => {
      clearTimeout(transformTimer);
      clearTimeout(mergeTimer);
      clearTimeout(moveTimer);
      clearTimeout(completeTimer);
    };
  }, [onComplete]);

  /*
   * ============================================================
   * FLIGHT PROGRESS
   * ============================================================
   */

  const progress = useMotionValue(0);

  /*
   * ============================================================
   * SINGLE CONTINUOUS BÉZIER CURVE
   * ============================================================
   */

  const curveStrength = 0.14;

  const curveX = useTransform(progress, (t) => {
    if (!target) return 0;

    const c1x = target.x * 0.25;
    const c2x = target.x * 0.78;

    const oneMinusT = 1 - t;

    return (
      3 *
        oneMinusT *
        oneMinusT *
        t *
        c1x +
      3 *
        oneMinusT *
        t *
        t *
        c2x +
      t *
        t *
        t *
        target.x
    );
  });

  const curveY = useTransform(progress, (t) => {
    if (!target) return 0;

    const distance = Math.sqrt(
      target.x * target.x +
        target.y * target.y
    );

    const curveAmount = Math.min(
      Math.max(distance * curveStrength, 35),
      100
    );

    const c1y =
      target.y * 0.18 +
      curveAmount;

    const c2y =
      target.y * 0.72 +
      curveAmount * 0.45;

    const oneMinusT = 1 - t;

    return (
      3 *
        oneMinusT *
        oneMinusT *
        t *
        c1y +
      3 *
        oneMinusT *
        t *
        t *
        c2y +
      t *
        t *
        t *
        target.y
    );
  });

  /*
   * ============================================================
   * IMPORTANT:
   *
   * Keep the original "-50%" centering transform.
   *
   * The curve is added ON TOP of it.
   *
   * This is what guarantees that the final position is the
   * exact same position as the old working animation.
   * ============================================================
   */

  const animatedX = useTransform(
    curveX,
    (x) => `calc(-50% + ${x}px)`
  );

  const animatedY = useTransform(
    curveY,
    (y) => `calc(-50% + ${y}px)`
  );

  /*
   * ============================================================
   * START FLIGHT
   * ============================================================
   *
   * IMPORTANT:
   * Use Framer Motion's animate() function rather than
   * progress.animate().
   */

  useEffect(() => {
    if (phase !== "move" || !target) return;

    progress.set(0);

    const controls = animate(
      progress,
      1,
      {
        duration: 1.25,
        ease: [0.12, 0.82, 0.25, 1],
      }
    );

    return () => {
      controls.stop();
    };
  }, [phase, target, progress]);

  /*
   * ============================================================
   * RENDER
   * ============================================================
   */

  return (
    <motion.div
      className="fixed inset-0 z-[9999] bg-black overflow-hidden"
      initial={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{
        duration: 0.55,
        ease: [0.22, 1, 0.36, 1],
      }}
    >
      <motion.div
        ref={splashWordRef}
        className="
          absolute
          left-1/2
          top-1/2
          flex
          items-center
          whitespace-nowrap
          text-xl
          sm:text-2xl
          md:text-3xl
          text-white
        "
        style={{
          ...TIMES_FONT,

          /*
           * Before flight:
           * exact center positioning.
           *
           * During flight:
           * exact center positioning + Bézier offset.
           */
          x:
            phase === "move"
              ? animatedX
              : "-50%",

          y:
            phase === "move"
              ? animatedY
              : "-50%",
        }}
      >
        {phase === "full" ||
        phase === "transform" ? (
          <>
            {/* VEH */}

            <motion.span
              className="text-white"
              style={TIMES_FONT}
            >
              veh
            </motion.span>

            {/* ICLES */}

            <motion.span
              className="text-white overflow-hidden"
              style={TIMES_FONT}
              animate={{
                opacity:
                  phase === "full"
                    ? 1
                    : 0,

                width:
                  phase === "full"
                    ? "auto"
                    : 0,
              }}
              transition={{
                opacity: {
                  duration: 1.15,
                  ease: [0.4, 0, 0.2, 1],
                },

                width: {
                  duration: 1.2,
                  ease: [0.65, 0, 0.35, 1],
                },
              }}
            >
              icles
            </motion.span>

            {/* PLUS */}

            <motion.span
              className="text-white overflow-hidden"
              style={TIMES_FONT}
              animate={{
                opacity:
                  phase === "full"
                    ? 1
                    : 0,

                width:
                  phase === "full"
                    ? "auto"
                    : 0,

                marginLeft:
                  phase === "full"
                    ? "0.28em"
                    : 0,

                marginRight:
                  phase === "full"
                    ? "0.28em"
                    : 0,
              }}
              transition={{
                opacity: {
                  duration: 0.9,
                  ease: [0.4, 0, 0.2, 1],
                },

                width: {
                  duration: 1.15,
                  ease: [0.65, 0, 0.35, 1],
                },

                marginLeft: {
                  duration: 1.15,
                  ease: [0.65, 0, 0.35, 1],
                },

                marginRight: {
                  duration: 1.15,
                  ease: [0.65, 0, 0.35, 1],
                },
              }}
            >
              +
            </motion.span>

            {/* COMMU */}

            <motion.span
              className="text-white overflow-hidden"
              style={TIMES_FONT}
              animate={{
                opacity:
                  phase === "full"
                    ? 1
                    : 0,

                width:
                  phase === "full"
                    ? "auto"
                    : 0,
              }}
              transition={{
                opacity: {
                  duration: 1.15,
                  ease: [0.4, 0, 0.2, 1],
                },

                width: {
                  duration: 1.2,
                  ease: [0.65, 0, 0.35, 1],
                },
              }}
            >
              commu
            </motion.span>

            {/* NICATE */}

            <motion.span
              className="text-white"
              style={TIMES_FONT}
            >
              nicate
            </motion.span>
          </>
        ) : (
          /*
           * ======================================================
           * CLEAN MERGED WORD
           * ======================================================
           */

          <motion.span
            className="
              text-xl
              sm:text-2xl
              md:text-3xl
              text-white
            "
            style={TIMES_FONT}
          >
            vehnicate
          </motion.span>
        )}
      </motion.div>
    </motion.div>
  );
}

/*
 * ================================================================
 * ROUTES
 * ================================================================
 */

function AnimatedRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait">
      <Routes
        location={location}
        key={location.pathname}
      >
        <Route
          path="/"
          element={
            <PageWrapper>
              <Home />
            </PageWrapper>
          }
        />

        <Route
          path="/waitlist"
          element={
            <PageWrapper>
              <WaitlistPage />
            </PageWrapper>
          }
        />

        <Route
          path="/map"
          element={
            <PageWrapper>
              <MapPage />
            </PageWrapper>
          }
        />
        <Route
          path="/Ellar"
          element={
            <PageWrapper>
              <Ellar />
            </PageWrapper>
          }
        />
      </Routes>
    </AnimatePresence>
  );
}

/*
 * ================================================================
 * PAGE TRANSITION
 * ================================================================
 */

function PageWrapper({ children }) {
  return (
    <motion.div
      initial={{
        opacity: 0,
        y: 20,
      }}
      animate={{
        opacity: 1,
        y: 0,
      }}
      exit={{
        opacity: 0,
        y: -20,
      }}
      transition={{
        duration: 0.4,
        ease: "easeInOut",
      }}
      className="min-h-screen"
    >
      {children}
    </motion.div>
  );
}

/*
 * ================================================================
 * APP
 * ================================================================
 */

function App() {
  const [showSplash, setShowSplash] = useState(() => {
    // Show splash when the site is opened/reloaded directly.
    // Internal navigation will not show it again.
    return !window.__appAlreadyLoaded;
  });

  const handleSplashComplete = useCallback(() => {
    window.__splashDone = true;
    window.__appAlreadyLoaded = true;

    window.dispatchEvent(new Event("splash-complete"));
    setShowSplash(false);
  }, []);

  useEffect(() => {
    const lenis = new Lenis({
      duration: 1.8,
      smoothWheel: true,
      wheelMultiplier: 0.55,
    });

    function raf(time) {
      lenis.raf(time);
      requestAnimationFrame(raf);
    }

    requestAnimationFrame(raf);

    return () => {
      lenis.destroy();
    };
  }, []);

  return (
    <div className="App">
      <AnimatedRoutes />

      <AnimatePresence>
        {showSplash && (
          <SplashScreen onComplete={handleSplashComplete} />
        )}
      </AnimatePresence>

      <Analytics />
    </div>
  );
}

export default App;

