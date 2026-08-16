import assert from "node:assert/strict";
import {
  MAX_OCCURRENCE_CROP_SIDE,
  OCCURRENCE_CROP_SCALE,
  computeOccurrenceCropGeometry,
} from "../../client/crop.js";

function geometry(sourceWidth, sourceHeight, boundingBox) {
  return computeOccurrenceCropGeometry({
    sourceWidth,
    sourceHeight,
    boundingBox,
  });
}

function provesCenteredSquareUsesTheLargestBboxDimension() {
  const result = geometry(1000, 800, {
    originX: 300,
    originY: 200,
    width: 100,
    height: 200,
  });

  assert.equal(result.requestedSide, 200 * OCCURRENCE_CROP_SCALE);
  assert.equal(result.requestedLeft, 230);
  assert.equal(result.requestedTop, 180);
  assert.equal(result.sourceX, 230);
  assert.equal(result.sourceY, 180);
  assert.equal(result.sourceWidth, 240);
  assert.equal(result.sourceHeight, 240);
  assert.equal(result.scale, 1);
  assert.equal(result.destinationWidth, 240);
  assert.equal(result.destinationHeight, 240);
}

function provesEdgeCropIsClippedWithoutCenterShiftOrPadding() {
  const result = geometry(400, 300, {
    originX: 0,
    originY: 0,
    width: 100,
    height: 100,
  });

  assert.equal(result.requestedSide, 120);
  assert.equal(result.requestedLeft, -10);
  assert.equal(result.requestedTop, -10);
  assert.equal(result.sourceX, 0);
  assert.equal(result.sourceY, 0);
  assert.equal(result.sourceWidth, 110);
  assert.equal(result.sourceHeight, 110);
  assert.equal(result.destinationWidth, 110);
  assert.equal(result.destinationHeight, 110);
}

function provesFractionalGeometryIsRetainedUntilCanvasDimensions() {
  const result = geometry(640, 480, {
    originX: 212.25,
    originY: 100.5,
    width: 80.5,
    height: 100.25,
  });

  assert.ok(Math.abs(result.requestedSide - 120.3) < 1e-9);
  assert.ok(Math.abs(result.requestedLeft - 192.35) < 1e-9);
  assert.ok(Math.abs(result.requestedTop - 90.475) < 1e-9);
  assert.ok(Math.abs(result.sourceWidth - 120.3) < 1e-9);
  assert.ok(Math.abs(result.sourceHeight - 120.3) < 1e-9);
  assert.equal(result.scale, 1);
  assert.equal(result.destinationWidth, 120);
  assert.equal(result.destinationHeight, 120);
}

function provesLargeCropsOnlyScaleDownToTheAcceptedBound() {
  const result = geometry(1600, 1200, {
    originX: 400,
    originY: 300,
    width: 400,
    height: 600,
  });

  assert.equal(result.requestedSide, 720);
  assert.equal(result.sourceWidth, 720);
  assert.equal(result.sourceHeight, 720);
  assert.equal(result.scale, MAX_OCCURRENCE_CROP_SIDE / 720);
  assert.equal(result.destinationWidth, MAX_OCCURRENCE_CROP_SIDE);
  assert.equal(result.destinationHeight, MAX_OCCURRENCE_CROP_SIDE);
}

function provesSmallCropsAreNeverUpscaled() {
  const result = geometry(320, 240, {
    originX: 40,
    originY: 50,
    width: 30,
    height: 40,
  });

  assert.equal(result.requestedSide, 48);
  assert.equal(result.scale, 1);
  assert.equal(result.destinationWidth, 48);
  assert.equal(result.destinationHeight, 48);
  assert.ok(result.destinationWidth < MAX_OCCURRENCE_CROP_SIDE);
}

function provesOutOfFrameBboxesAreRejected() {
  assert.throws(
    () =>
      geometry(320, 240, {
        originX: 400,
        originY: 50,
        width: 30,
        height: 40,
      }),
    /does not intersect source frame/,
  );
}

provesCenteredSquareUsesTheLargestBboxDimension();
provesEdgeCropIsClippedWithoutCenterShiftOrPadding();
provesFractionalGeometryIsRetainedUntilCanvasDimensions();
provesLargeCropsOnlyScaleDownToTheAcceptedBound();
provesSmallCropsAreNeverUpscaled();
provesOutOfFrameBboxesAreRejected();
console.log(
  "crop geometry GREEN: centered 1.2x square, edge clipping, fractional coordinates, 512px proportional bound and no upscale",
);
