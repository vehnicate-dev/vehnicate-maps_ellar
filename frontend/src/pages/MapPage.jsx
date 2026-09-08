import RoadDefectsMap from "../components/map/RoadDefectsMap"

const FOOTER_HEIGHT = 64
const PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=com.vehnway.app"

const MapPage = () => {
  return (
    <div
      className="flex flex-col bg-black overflow-hidden"
      style={{
        height: "100dvh",
        overscrollBehavior: "none",
        touchAction: "none",
      }}
    >
      {/* Map */}
      <div
        className="relative"
        style={{
          height: `calc(100dvh - ${FOOTER_HEIGHT}px)`,
          overscrollBehavior: "none",
        }}
      >
        <RoadDefectsMap />
      </div>

      {/* Footer */}
      <footer
        className="bg-black border-t border-purple-500/20 flex items-center justify-center text-center px-4"
        style={{
          height: `${FOOTER_HEIGHT}px`,
          flexShrink: 0,
          overscrollBehavior: "none",
          touchAction: "none",
        }}
      >
        <p className="text-gray-400 text-sm md:text-base">
          Don't find your place?{" "}
          <a href={PLAY_STORE_URL} target="_blank" rel="noopener noreferrer">
            <span className="bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent font-medium cursor-pointer hover:opacity-80 transition-opacity">
              Download the vehnicate app
            </span>
          </a>{" "}
          and drive through your area to put it on the map.
        </p>
      </footer>
    </div>
  )
}

export default MapPage