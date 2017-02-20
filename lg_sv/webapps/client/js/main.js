var showLinks = getParameterByName('showLinks', stringToBoolean, false);
var yawOffset = getParameterByName('yawOffset', Number, 0);
var pitchOffset = getParameterByName('pitchOffset', Number, 0);
var fieldOfView = getParameterByName('fov', Number, 29);
var initialPano = getParameterByName('panoid', String, '');
var rosbridgeHost = getParameterByName('rosbridgeHost', String, 'localhost');
var rosbridgePort = getParameterByName('rosbridgePort', String, '9090');
var rosbridgeSecure = getParameterByName('rosbridgeSecure', stringToBoolean, 'false');
// Find default scaleFactor (devicePixelRatio) setting in index.html.
var scaleFactor = getParameterByName('scaleFactor', Number, window.devicePixelRatio);
var scaleMatrix = [
  [scaleFactor, 0, 0, 0],
  [0, scaleFactor, 0, 0],
  [0, 0, 1, 0],
  [0, 0, 0, 1]
];
var lastPov = null;
if (showLinks) {
  var glEnvironment;
  var links;
}

var initialize = function() {
  console.log('initializing Street View');

  var url = getRosbridgeUrl(rosbridgeHost, rosbridgePort, rosbridgeSecure);
  var ros = new ROSLIB.Ros({
    url: url
  });
  ros.on('connection', function() {
    console.log('ROSLIB connected');
    initializeRes(ros);
  });
  ros.on('error', function() {
    setTimeout(initialize, 2000);
  });
  if (showLinks) {
    glEnvironment = new GLEnvironment(fieldOfView);
    links = new Links(glEnvironment.camera, glEnvironment.scene);
  }
};

var initializeRes = function(ros) {
  var panoTopic = new ROSLIB.Topic({
    ros: ros,
    name: '/streetview/panoid',
    messageType: 'std_msgs/String'
  });
  var metadataTopic = new ROSLIB.Topic({
    ros: ros,
    name: '/streetview/metadata',
    messageType: 'std_msgs/String'
  });

  var attributionModule = new Attribution(document.getElementById('info'));
  var handleMetadataResponse = function(response, stat) {
    if (stat != google.maps.StreetViewStatus.OK) {
      throw 'Metadata request status NOT OK: ' + stat;
    }
    attributionModule.handleMetadata(response);
    if (showLinks) {
      links.update(response);
    }
  };

  var handlePanoIdMsg = function(msg) {
    $("#titlecard").hide();
  };

  panoTopic.subscribe(handlePanoIdMsg);

  var mapOptions = {
    disableDefaultUI: true,
    center: new google.maps.LatLng(45, 45),
    backgroundColor: 'black',
    zoom: 8
  };
  var svOptions = {
    visible: true,
    disableDefaultUI: true
  };
  var canvas = $('#map-canvas');
  var map = new google.maps.Map(canvas[0], mapOptions);
  var sv = new google.maps.StreetViewPanorama(canvas[0], svOptions);

  map.setStreetView(sv);

  var svClient = new StreetviewClient(ros, sv);

  var svService = new google.maps.StreetViewService();

  svClient.on('pano_changed', function(panoId) {
    sv.setPano(panoId);
    var fovFudge = getFovFudge(fieldOfView);
    var zoomLevel = getZoomLevel(fieldOfView * scaleFactor * fovFudge);
    sv.setZoom(zoomLevel);
    if (lastPov) {
      lastPov.w = 70;
      svClient.pubPov(lastPov);
    }
    svService.getPanorama({ pano: panoId }, handleMetadataResponse);
  });

  /**
   * Get the zoom level at a given horizontal fov.
   *
   * This is only correct at scaleFactor 1.0.
   *
   * @param {Number} hFov in degrees
   * @return {Number} zoom level
   */
  function getZoomLevel(hFov) {
    return -Math.log2(Math.tan(Math.PI * hFov / 360)) + 1;
  }

  /**
   * Multiply two matrices.
   *
   * <http://stackoverflow.com/a/27205341>
   *
   * @param a left matrix
   * @param b right matrix
   * @return result matrix
   */
  function multiply(a, b) {
    var aNumRows = a.length, aNumCols = a[0].length,
        bNumRows = b.length, bNumCols = b[0].length,
        m = new Array(aNumRows);  // initialize array of rows
    for (var r = 0; r < aNumRows; ++r) {
      m[r] = new Array(bNumCols); // initialize the current row
      for (var c = 0; c < bNumCols; ++c) {
        m[r][c] = 0;              // initialize the current cell
        for (var i = 0; i < aNumCols; ++i) {
          m[r][c] += a[r][i] * b[i][c];
        }
      }
    }
    return m;
  }

  /**
   * Builds the transform matrix to scale and rotate a canvas.
   *
   * @param {Array} scaleMatrix
   * @param {Number} roll in radians
   * @return {String} transform matrix CSS
   */
  function buildTransformMatrix(scaleMatrix, roll) {
    var sr = Math.sin(roll);
    var cr = Math.cos(roll);
    var rotationMatrix = [
      [cr, -sr, 0, 0],
      [sr, cr, 0, 0],
      [0, 0, 1, 0],
      [0, 0, 0, 1]
    ];

    var finalMatrix = multiply(rotationMatrix, scaleMatrix);
    var flatMatrix = Array.prototype.concat.apply([], finalMatrix);

    var cssTransform = ['matrix3d(', flatMatrix.join(), ')'].join(' ');
    return cssTransform;
  };

  var wrapper = document.getElementById('wrapper');

  /**
   * Handles an incoming pov change.
   *
   * @param {Object} povQuaternion with keys {x, y, z, w}
   **/
  var handleQuaternion = function(povQuaternion) {
    lastPov = povQuaternion;
    // TODO(mv): move quaternion parsing into StreetviewClient library
    var radianOffset = toRadians(fieldOfView * yawOffset);

    var htr = [povQuaternion.z, povQuaternion.x, 0];
    var transformedHTR = transformHTR(htr, radianOffset);

    var heading = transformedHTR[0];
    var tilt = transformedHTR[1];
    var roll = transformedHTR[2];

    var pov = {
      heading: heading,
      pitch: tilt
    };
    sv.setPov(pov);

    var rollRads = toRadians(roll);
    wrapper.style.transform = buildTransformMatrix(scaleMatrix, rollRads);

    if (showLinks) {
      links.handleView(heading, tilt, roll, fieldOfView);
    }
  };
  svClient.on('pov_changed', handleQuaternion);

  if (initialPano !== '') {
    svClient.emit('pano_changed', initialPano);
  }

  if (showLinks) {
    glEnvironment.run();
  }
};

google.maps.event.addDomListener(window, 'load', initialize);

// # vim: tabstop=8 expandtab shiftwidth=2 softtabstop=2
