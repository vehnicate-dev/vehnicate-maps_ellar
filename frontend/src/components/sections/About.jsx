import React, { useState, useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";

const gradientText =
  "bg-gradient-to-r from-purple-400 via-pink-500 to-purple-400 bg-clip-text text-transparent";

const PLAYSTORE_URL =
  "https://play.google.com/store/apps/details?id=com.vehnway.app&pcampaignid=web_share";

const TOTAL_STEPS = 4;
const VH_PER_STEP = 100;

const StepCard = ({ index, total, scrollYProgress, children }) => {
  const segment = 1 / total;

  const start = index * segment;
  const end = start + segment;

  const y = useTransform(
    scrollYProgress,
    [start, end],
    ["0%", "-130%"]
  );

  const rotate = useTransform(
    scrollYProgress,
    [start, end],
    [0, -6]
  );

  const scale = useTransform(
    scrollYProgress,
    [start, end],
    [1, 0.96]
  );

  const opacity = useTransform(
    scrollYProgress,
    [start, start + segment * 0.65, end],
    [1, 1, 0]
  );

  return (
    <motion.div
      style={{
        y,
        rotate,
        scale,
        opacity,
        zIndex: total - index,
      }}
      className="
        absolute
        inset-0
        rounded-[28px]
        bg-[#f3ead8]
        shadow-[0_20px_50px_-20px_rgba(0,0,0,0.65)]
        flex
        items-center
        justify-center
        overflow-hidden
        px-8
        sm:px-12
      "
    >
      {/* subtle vertical paper crease */}
      <div
        className="
          pointer-events-none
          absolute
          top-0
          left-[18%]
          w-[1px]
          h-full
          bg-black/[0.035]
          rotate-[2deg]
        "
      />

      {/* subtle highlight crease */}
      <div
        className="
          pointer-events-none
          absolute
          top-0
          right-[24%]
          w-[1px]
          h-full
          bg-white/40
          rotate-[-1deg]
        "
      />

      {/* subtle horizontal crease */}
      <div
        className="
          pointer-events-none
          absolute
          left-0
          top-[28%]
          w-full
          h-[1px]
          bg-black/[0.025]
          rotate-[-1deg]
        "
      />

      {/* folded paper corner */}
      <div
        className="
          pointer-events-none
          absolute
          top-0
          right-0
          w-12
          h-12
          bg-[#e5dac5]
          [clip-path:polygon(100%_0,100%_100%,0_0)]
          opacity-60
        "
      />

      <div className="relative z-10 w-full max-w-xl text-center">
        {children}
      </div>
    </motion.div>
  );
};

const StepNumber = ({ n }) => (
  <div className="flex justify-center mb-4">
    <span
      className="
        font-ledger
        text-4xl
        sm:text-5xl
        font-semibold
        tracking-tight
        text-gray-900
      "
    >
      {n}
    </span>
  </div>
);

const About = () => {
  const [hasPhoneMount, setHasPhoneMount] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const selectedOption = hasPhoneMount ? "yupp" : "nopee";
  const oppositeOption = hasPhoneMount ? "nopee" : "yupp";

  const handleOptionSelect = (value) => {
    setHasPhoneMount(value === "yupp");
    setDropdownOpen(false);
  };

  const sectionRef = useRef(null);

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end end"],
  });

  return (
    <section
      id="app"
      ref={sectionRef}
      style={{ height: `${TOTAL_STEPS * VH_PER_STEP}vh` }}
      className="
        relative
        bg-gradient-to-b
        from-black
        via-purple-900/5
        to-black
      "
    >
      {/* background glow */}
      <div
        className="
          pointer-events-none
          absolute
          inset-0
          overflow-hidden
        "
      >
        <div
          className="
            absolute
            top-[15%]
            left-[10%]
            w-[350px]
            h-[350px]
            rounded-full
            bg-purple-600/10
            blur-[120px]
          "
        />

        <div
          className="
            absolute
            bottom-[15%]
            right-[10%]
            w-[300px]
            h-[300px]
            rounded-full
            bg-pink-600/10
            blur-[120px]
          "
        />
      </div>

      {/* pinned viewport */}
      <div
        className="
          sticky
          top-0
          h-screen
          overflow-hidden
          flex
          items-center
        "
      >
        <div
          className="
            max-w-7xl
            w-full
            mx-auto
            px-4
            sm:px-6
            lg:px-8
            relative
            z-10
          "
        >
          {/* title */}
          <div className="text-left mb-8 sm:mb-10">
            <div className="inline-block">
              <h2
                className="
                  font-ledger
                  text-4xl
                  sm:text-5xl
                  md:text-6xl
                  font-semibold
                  tracking-tight
                  text-white
                  whitespace-nowrap
                "
              >
                the{" "}
                <span className={gradientText}>
                  mobile app
                </span>
              </h2>

              {/* underline */}
              <div className="mt-3 flex items-center w-full">
                <div className="h-px flex-1 bg-white/40" />
                <div className="ml-1.5 w-1.5 h-1.5 rounded-full bg-white/70" />
              </div>
            </div>
          </div>

          {/* two-column layout */}
          <div
            className="
              flex
              flex-col
              lg:flex-row
              gap-8
              lg:gap-16
              items-center
            "
          >
            {/* step cards */}
            <div className="w-full lg:w-1/2">
              <div
                className="
                  relative
                  w-full
                  max-w-2xl
                  h-64
                  sm:h-72
                  mx-auto
                "
              >
                {/* STEP 1 */}
                <StepCard
                  index={0}
                  total={TOTAL_STEPS}
                  scrollYProgress={scrollYProgress}
                >
                  <StepNumber n="01" />

                  <div className="flex flex-col items-center text-gray-900">
                    <h3
                      className="
                        font-ledger
                        text-xl
                        sm:text-2xl
                        font-semibold
                        mb-3
                      "
                    >
                      install the app
                    </h3>

                    <p
                      className="
                        text-sm
                        sm:text-base
                        leading-relaxed
                        text-gray-600
                        max-w-md
                      "
                    >
                      Install our android app{" "}
                      <a
                        href={PLAYSTORE_URL}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="
                          text-purple-600
                          underline
                          decoration-purple-400/60
                          hover:text-pink-600
                          transition-colors
                          duration-300
                        "
                      >
                        here
                      </a>
                      .
                    </p>
                  </div>
                </StepCard>

                {/* STEP 2 */}
                <StepCard
                  index={1}
                  total={TOTAL_STEPS}
                  scrollYProgress={scrollYProgress}
                >
                  <div className="flex items-start justify-center gap-2 sm:gap-5">
                    {/* bike */}
                    <img
                      src="/phone_on_bike.png"
                      alt="Phone mounted on a bike"
                      className="
                        w-16
                        sm:w-20
                        h-16
                        sm:h-20
                        object-contain
                        flex-shrink-0
                        -translate-y-4
                        sm:translate-y--1
                      "
                    />

                    {/* number + question */}
                    <div className="flex flex-col items-center text-gray-900 min-w-0">
                      <StepNumber n="02" />

                      <h3
                        className="
                          font-ledger
                          text-lg
                          sm:text-2xl
                          font-semibold
                          leading-tight
                          text-center
                          whitespace-nowrap
                        "
                      >
                        do you have a phone mount?
                      </h3>
                    </div>

                    {/* car */}
                    <img
                      src="/phone_on_car2.png"
                      alt="Phone mounted in a car"
                      className="
                        w-16
                        sm:w-20
                        h-16
                        sm:h-20
                        object-contain
                        flex-shrink-0
                        -translate-y-4
                        sm:translate-y--1
                      "
                    />
                  </div>

                  <div className="flex flex-col items-center text-gray-900 mt-5">
                    <div className="relative w-full max-w-xs">
                      {/* dropdown button */}
                      <button
                        type="button"
                        onClick={() => setDropdownOpen((prev) => !prev)}
                        className="
                          w-full
                          flex
                          items-center
                          justify-between
                          rounded-full
                          px-5
                          py-3
                          bg-[#e8decb]
                          border
                          border-black/10
                          text-gray-800
                          text-sm
                          font-medium
                          shadow-sm
                          hover:bg-[#e3d7c2]
                          transition-colors
                        "
                      >
                        <span className="flex-1 text-center">
                          {selectedOption}
                        </span>

                        <span
                          className={`
                            ml-3
                            text-gray-700
                            text-xs
                            transition-transform
                            duration-200
                            ${dropdownOpen ? "rotate-180" : ""}
                          `}
                        >
                          ▼
                        </span>
                      </button>

                      {/* dropdown menu */}
                      {dropdownOpen && (
                        <div
                          className="
                            absolute
                            z-50
                            left-0
                            right-0
                            mt-2
                            rounded-2xl
                            bg-[#f8f3e9]
                            border
                            border-black/10
                            shadow-[0_12px_30px_-12px_rgba(0,0,0,0.35)]
                            overflow-hidden
                          "
                        >
                          <button
                            type="button"
                            onClick={() => handleOptionSelect(oppositeOption)}
                            className="
                              w-full
                              px-5
                              py-3
                              text-sm
                              text-gray-800
                              hover:bg-[#eee5d5]
                              transition-colors
                            "
                          >
                            {oppositeOption}
                          </button>
                        </div>
                      )}
                    </div>

                    <p
                      className="
                        mt-5
                        text-sm
                        sm:text-base
                        leading-relaxed
                        text-gray-600
                        max-w-md
                        text-center
                      "
                    >
                      {hasPhoneMount ? (
                        <>
                          Mount your phone on your mount and
                          start drive.
                        </>
                      ) : (
                        <>
                          No worries. Start drive and keep your phone in your
                          pocket and let vehnicate do the rest.
                        </>
                      )}
                    </p>
                  </div>
                </StepCard>

                {/* STEP 3 */}
                <StepCard
                  index={2}
                  total={TOTAL_STEPS}
                  scrollYProgress={scrollYProgress}
                >
                  <StepNumber n="03" />

                  <div className="flex flex-col items-center text-gray-900">
                    <h3
                      className="
                        font-ledger
                        text-xl
                        sm:text-2xl
                        font-semibold
                        mb-3
                      "
                    >
                      drive like you normally do
                    </h3>

                    <p
                      className="
                        text-sm
                        sm:text-base
                        leading-relaxed
                        text-gray-600
                        max-w-md
                      "
                    >
                      Just drive as always.
                      Once you are done with your trip, all the potholes and speedbreakers you drove
                      over will be put on the map!
                    </p>
                  </div>
                </StepCard>

                {/* STEP 4 */}
                <StepCard
                  index={3}
                  total={TOTAL_STEPS}
                  scrollYProgress={scrollYProgress}
                >
                  <StepNumber n="04" />

                  <div className="flex flex-col items-center text-gray-900">
                    <h3
                      className="
                        font-ledger
                        text-xl
                        sm:text-2xl
                        font-semibold
                        mb-3
                      "
                    >
                      earn{" "}
                      <span className={gradientText}>
                        Ellars
                      </span>
                    </h3>

                    <p
                      className="
                        text-sm
                        sm:text-base
                        leading-relaxed
                        text-gray-600
                        max-w-md
                      "
                    >
                      Every useful road-defect contributes
                      to your{" "}
                      <span className={gradientText}>
                        Ellar
                      </span>{" "}
                      balance - rewarding you for helping make
                      roads safer.
                    </p>
                  </div>
                </StepCard>
              </div>
            </div>

            {/* phone */}
            <div
              className="
                w-full
                lg:w-1/2
                flex
                justify-center
                items-center
                relative
              "
            >
              {/* decorative rotating graphic */}
              <motion.img
                src="/gggyrate.svg"
                alt=""
                aria-hidden="true"
                className="
                  absolute
                  w-[280px]
                  sm:w-[340px]
                  md:w-[400px]
                  lg:w-[460px]
                  max-w-none
                  opacity-40
                  pointer-events-none
                  select-none
                "
                animate={{
                  rotate: 360,
                }}
                transition={{
                  duration: 35,
                  repeat: Infinity,
                  ease: "linear",
                }}
              />

              {/* phone image */}
              <motion.div
                className="
                  relative
                  z-10
                  flex
                  justify-center
                  items-center
                "
                animate={{
                  y: [0, -8, 0],
                }}
                transition={{
                  duration: 4,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
              >
                <img
                  src="/app_homepage.png"
                  alt="vehnicate mobile app"
                  className="
                    relative
                    w-[190px]
                    sm:w-[220px]
                    md:w-[250px]
                    lg:w-[280px]
                    h-auto
                    object-contain
                    drop-shadow-[0_25px_40px_rgba(0,0,0,0.45)]
                  "
                  onError={(e) => {
                    e.currentTarget.style.display = "none";
                  }}
                />
              </motion.div>
            </div>
          </div>

          {/* tip */}
          <p
            className="
              mt-5
              sm:mt-6
              text-center
              text-xs
              sm:text-sm
              text-gray-500
              font-mono
            "
          >
            Tip: Mounting your phone on a phone mount gets you
            twice as much Ellars as keeping it in your pocket.
          </p>
        </div>
      </div>
    </section>
  );
};

export default About;