import RoadDefectsMap from "../components/map/RoadDefectsMap"

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
          height: "100dvh",
          overscrollBehavior: "none",
        }}
      >
        <RoadDefectsMap />
      </div>
    </div>
  )
}

export default MapPage