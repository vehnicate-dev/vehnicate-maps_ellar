import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";

const gradientText =
  "bg-gradient-to-r from-purple-400 via-pink-500 to-purple-400 bg-clip-text text-transparent";

const Working = () => {
  return (
    <section
      id="working"
      className="
        py-12
        sm:py-16
        md:py-20
        bg-gradient-to-b
        from-black
        via-purple-900/5
        to-black
        relative
        overflow-hidden
      "
    >
      {/* Background light blobs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div
          className="
            absolute
            top-20
            -right-16
            sm:-right-24
            lg:-right-32
            w-48
            h-48
            sm:w-72
            sm:h-72
            lg:w-96
            lg:h-96
            bg-gradient-to-l
            from-purple-600/25
            to-pink-600/15
            rounded-full
            blur-3xl
            opacity-80
          "
        />

        <div
          className="
            absolute
            bottom-20
            -left-16
            sm:-left-24
            lg:-left-32
            w-40
            h-40
            sm:w-60
            sm:h-60
            lg:w-80
            lg:h-80
            bg-gradient-to-r
            from-pink-600/25
            to-purple-600/15
            rounded-full
            blur-3xl
            opacity-80
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
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          viewport={{ once: true }}
          className="text-left mb-10 sm:mb-12 lg:mb-16"
        >
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
              <span className={gradientText}>You</span>{" "}
              and the{" "}
              <span className={gradientText}>Ellar</span>
            </h2>

            {/* underline */}
            <div className="mt-3 flex items-center w-full">
              <div className="h-px flex-1 bg-white/40" />
              <div className="ml-1.5 w-1.5 h-1.5 rounded-full bg-white/70" />
            </div>
          </div>
        </motion.div>

        {/* Main content */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.1 }}
          viewport={{ once: true }}
          className="
            w-full
            text-left
            font-ledger
            text-gray-300
            leading-relaxed
            space-y-5
            text-base
            sm:text-lg
            lg:text-xl
            max-w-5xl
          "
        >
          <p>
            Every time you drive over a road defect with our app on, it gives
            us information which would be used to alert future drivers on
            that hazard. This act of saving a life has a positive emotional
            impact on their family and a positive economic impact on the
            nation as a whole.
          </p>

          <p>
            And we wanted a way to channel this economic benefit straight to
            "you" - a shareholder that should hold a chunk of the growth that
            comes out of this process.
          </p>

          <p className="text-white font-medium">
            That is precisely why the{" "}
            <span className={`${gradientText} font-semibold`}>
              Ellar
            </span>{" "}
            exists.
          </p>

          {/* Ellar page link */}
          <p className="pt-3 text-gray-400">
            If you wish to know more about the history and the working of the
            Ellar,{" "}
            <Link
              to="/Ellar"
              className="
                text-purple-400
                underline
                decoration-purple-400/50
                underline-offset-4
                hover:text-pink-400
                transition-colors
                duration-300
              "
            >
              visit this page
            </Link>
            .
          </p>
        </motion.div>
      </div>
    </section>
  );
};

export default Working;