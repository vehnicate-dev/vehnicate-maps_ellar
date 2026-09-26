import React from "react";
import { motion } from "framer-motion";

const gradientText =
  "bg-gradient-to-r from-purple-400 via-pink-500 to-purple-400 bg-clip-text text-transparent";

const Working = () => {
  return (
    <section
      id="working"
      className="py-12 sm:py-16 md:py-20 bg-gradient-to-b from-black via-purple-900/5 to-black relative overflow-hidden"
    >
      {/* Background light blobs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 -right-16 sm:-right-24 lg:-right-32 w-48 h-48 sm:w-72 sm:h-72 lg:w-96 lg:h-96 bg-gradient-to-l from-purple-600/25 to-pink-600/15 rounded-full blur-3xl opacity-80" />
        <div className="absolute bottom-20 -left-16 sm:-left-24 lg:-left-32 w-40 h-40 sm:w-60 sm:h-60 lg:w-80 lg:h-80 bg-gradient-to-r from-pink-600/25 to-purple-600/15 rounded-full blur-3xl opacity-80" />
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Title */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          viewport={{ once: true }}
          className="text-center mb-16 sm:mb-20 lg:mb-24"
        >
          <h2 className="text-3xl sm:text-4xl md:text-5xl lg:text-6xl xl:text-7xl 2xl:text-8xl font-ledger font-bold text-white leading-tight">
            The <span className={gradientText}>Ellar</span>
          </h2>
        </motion.div>

        {/* Sub-section 1: Why the name "Ellar"? */}
        <div className="mb-16 sm:mb-20 lg:mb-24">
          <motion.h3
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
            viewport={{ once: true }}
            className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-bold font-ledger text-white text-left mb-6 sm:mb-8 lg:mb-10"
          >
            Why the name "Ellar"?
          </motion.h3>

          <div className="flex flex-col lg:flex-row items-center gap-10 lg:gap-16">
            {/* Left: Text */}
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.15 }}
              viewport={{ once: true }}
              className="w-full lg:w-1/2 text-left font-ledger text-gray-300 leading-relaxed space-y-4 text-base sm:text-lg lg:text-xl"
            >
              <p>
                Legend has it that a Chola prince once ran over a calf with his chariot.
                When the cow pleaded for justice, the king executed his own son the same way -
                earning the title Manu Needhi Cholan.
              </p>
              <p>
                In a time where we encounter cases such as the Pune Porsche
                incident, this story of the Chola king has inspired vehnicate.
                In order to honour the king, the Ellar was named after him, whose
                original name was Ellalan - {" "}
                <span className={`${gradientText} font-semibold`}>
                  "the one who rules the boundary"
                </span>
                .
              </p>
            </motion.div>

            {/* Right: Image with background */}
            <div className="w-full lg:w-1/2 flex justify-center items-center relative">
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(147,51,234,0.15)_0%,rgba(236,72,153,0.08)_45%,transparent_70%)] pointer-events-none" />

              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                whileInView={{ opacity: 1, scale: 1 }}
                transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
                viewport={{ once: true }}
                className="relative z-10 w-full max-w-xs sm:max-w-sm lg:max-w-md"
              >
                <img
                  src="/Ellalan.jpg"
                  alt="King Ellalan"
                  className="w-full h-auto object-contain rounded-2xl shadow-2xl shadow-purple-500/20"
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

        {/* Sub-section 2: The purpose behind the Ellar */}
        <div>
          <motion.h3
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
            viewport={{ once: true }}
            className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-bold font-ledger text-white text-left mb-6 sm:mb-8 lg:mb-10"
          >
            The purpose behind the Ellar
          </motion.h3>

          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.15 }}
            viewport={{ once: true }}
            className="w-full text-left font-ledger text-gray-300 leading-relaxed space-y-4 text-base sm:text-lg lg:text-xl"
          >
            <p>
              Every time you drive over a road defect with our app on, it
              gives us information which would be used to alert future
              drivers on that hazard. This act of saving a life has a
              positive emotional impact on their family and a positive
              economic impact on the nation as a whole.
            </p>
            <p>
              And we wanted a way to channel this economic benefit straight
              to "you" - a shareholder that should hold a chunk of the
              growth that comes out of this process.
            </p>
            <p className="text-white font-medium">
              That is precisely why the{" "}
              <span className={`${gradientText} font-semibold`}>Ellar</span>{" "}
              exists.
            </p>
          </motion.div>
        </div>
      </div>
    </section>
  );
};

export default Working;