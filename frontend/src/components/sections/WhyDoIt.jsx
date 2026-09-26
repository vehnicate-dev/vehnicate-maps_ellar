import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

const gradientText =
  "bg-gradient-to-r from-purple-400 via-pink-500 to-purple-400 bg-clip-text text-transparent";

const rotatingWords = [
  "mother",
  "father",
  "wife",
  "husband",
  "friend",
  "sister",
  "brother",
  "daughter",
  "son",
];

const WhyDoIt = () => {
  const [currentWordIndex, setCurrentWordIndex] = useState(0);

  useEffect(() => {
    const wordInterval = setInterval(() => {
      setCurrentWordIndex((prev) => (prev + 1) % rotatingWords.length);
    }, 2500);
    return () => clearInterval(wordInterval);
  }, []);

  return (
    <section
      id="why"
      className="py-16 lg:py-24 bg-gradient-to-b from-black via-purple-900/5 to-black relative overflow-hidden"
    >
      {/* Background blobs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 -left-32 w-72 h-72 bg-gradient-to-r from-purple-600/10 to-pink-600/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 -right-32 w-72 h-72 bg-gradient-to-l from-pink-600/10 to-purple-600/10 rounded-full blur-3xl" />
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10 w-full">
        <div className="w-full text-center lg:text-left space-y-6 sm:space-y-8">
          {/* Heading */}
          <div className="inline-block">
            <motion.h2
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8 }}
              viewport={{ once: true }}
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
              why we <span className={gradientText}>care</span>
            </motion.h2>

            {/* underline */}
            <div className="mt-3 flex items-center w-full">
              <div className="h-px flex-1 bg-white/40" />
              <div className="ml-1.5 w-1.5 h-1.5 rounded-full bg-white/70" />
            </div>
          </div>
          
          {/* Copy */}
          <div className="font-ledger text-gray-300 leading-relaxed w-full">
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.1 }}
              viewport={{ once: true }}
              className="text-lg sm:text-xl lg:text-2xl xl:text-3xl"
            >
              <div>Somewhere out there, there's someone waiting for their</div>

              <div className="relative h-[1.3em] sm:h-[1.4em] overflow-hidden my-1 sm:my-2">
                <AnimatePresence mode="wait">
                  <motion.span
                    key={currentWordIndex}
                    initial={{ opacity: 0, y: 20, filter: "blur(4px)" }}
                    animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                    exit={{ opacity: 0, y: -20, filter: "blur(4px)" }}
                    transition={{ duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] }}
                    className={`${gradientText} font-semibold absolute inset-0 flex items-center justify-center lg:justify-start whitespace-nowrap text-2xl sm:text-3xl lg:text-4xl xl:text-5xl`}
                  >
                    {rotatingWords[currentWordIndex]}
                  </motion.span>
                </AnimatePresence>
              </div>

              <div>
                to return home safely, and in between stands potholes,
                speedbreakers and other drivers.
              </div>
            </motion.div>

            <motion.p
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.4 }}
              viewport={{ once: true }}
              className="text-lg sm:text-xl lg:text-2xl xl:text-3xl text-white mt-10 sm:mt-14 lg:mt-16"
            >
              And if a tomato can reach your door safely in 10 minutes,
              <br />
              We believe{" "}
              <span className={`${gradientText} font-bold`}>
                your person
              </span>{" "}
              must overcome these obstacles to reach you safely too.
            </motion.p>
          </div>
        </div>
      </div>
    </section>
  );
};

export default WhyDoIt;