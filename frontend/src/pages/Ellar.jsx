import React from "react";
import { motion } from "framer-motion";

const gradientText =
  "bg-gradient-to-r from-purple-400 via-pink-500 to-purple-400 bg-clip-text text-transparent";

const Ellar = () => {
  return (
    <section
      className="
        min-h-screen
        bg-gradient-to-b
        from-black
        via-purple-900/5
        to-black
        relative
        overflow-hidden
        py-12
        sm:py-16
        md:py-20
      "
    >
      {/* Background glow */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div
          className="
            absolute
            top-[10%]
            right-[5%]
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
            bottom-[10%]
            left-[5%]
            w-[300px]
            h-[300px]
            rounded-full
            bg-pink-600/10
            blur-[120px]
          "
        />
      </div>

      <div
        className="
          max-w-7xl
          mx-auto
          px-4
          sm:px-6
          lg:px-8
          relative
          z-10
        "
      >
        {/* Title */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          className="text-left mb-12 sm:mb-16 lg:mb-20"
        >
          <div className="inline-block">
            <h1
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
              The <span className={gradientText}>Ellar</span>
            </h1>

            {/* underline */}
            <div className="mt-3 flex items-center w-full">
              <div className="h-px flex-1 bg-white/40" />
              <div className="ml-1.5 w-1.5 h-1.5 rounded-full bg-white/70" />
            </div>
          </div>
        </motion.div>

        {/* History */}
        <div className="flex flex-col lg:flex-row items-center gap-10 lg:gap-16">
          {/* Text */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.15 }}
            className="
              w-full
              lg:w-1/2
              text-left
              font-ledger
              text-gray-300
              leading-relaxed
              space-y-5
              text-base
              sm:text-lg
              lg:text-xl
            "
          >
            <p>
              Legend has it that a Chola prince once ran over a calf with his
              chariot. When the cow pleaded for justice, the king executed
              his own son the same way - earning the title{" "}
              <span className="text-white font-medium">
                Manu Needhi Cholan
              </span>
              .
            </p>

            <p>
              In a time where we encounter cases such as the Pune Porsche
              incident, this story of the Chola king has inspired vehnicate.
              In order to honour the king, the Ellar was named after him,
              whose original name was Ellalan -{" "}
              <span className={`${gradientText} font-semibold`}>
                "the one who rules the boundary"
              </span>
              .
            </p>
          </motion.div>

          {/* King image */}
          <div className="w-full lg:w-1/2 flex justify-center items-center relative">
            <div
              className="
                absolute
                inset-0
                bg-[radial-gradient(ellipse_at_center,rgba(147,51,234,0.15)_0%,rgba(236,72,153,0.08)_45%,transparent_70%)]
                pointer-events-none
              "
            />

            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{
                duration: 1,
                ease: [0.16, 1, 0.3, 1],
              }}
              className="
                relative
                z-10
                w-full
                max-w-xs
                sm:max-w-sm
                lg:max-w-md
              "
            >
              <img
                src="/Ellalan.jpg"
                alt="King Ellalan"
                className="
                  w-full
                  h-auto
                  object-contain
                  rounded-2xl
                  shadow-2xl
                  shadow-purple-500/20
                "
                onError={(e) => {
                  e.target.onerror = null;
                  e.target.src =
                    "https://placehold.co/400x500/000000/FFFFFF?text=Ellalan";
                }}
              />
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default Ellar;