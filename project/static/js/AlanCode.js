// http://jsfiddle.net/Behseini/p5mJw/3/ for reference

function initMap(){

  // Initializing variables to be used
  var all_overlays = []
  var coordinatesArray = [];
  var selectedShape
  var map;
  var options;
  var markers;

  // For the shapes
  function clearSelection() {
    if (selectedShape) {
      selectedShape.setEditable(false);
      selectedShape = null;
    }
  }

  function setSelection(shape) {
    clearSelection();
    selectedShape = shape;
    shape.setEditable(true);

  }

  function deleteSelectedShape() {
    if (selectedShape) {
      selectedShape.setMap(null);
    }
  }

  function deleteAllShape() {
    for (var i = 0; i < all_overlays.length; i++) {
      all_overlays[i].overlay.setMap(null);
    }
    all_overlays = [];
  }



  // Map options
  options = {
    zoom:7,
    center:{lat:37.3021,lng:-120.47734}
  }

  // Initializing new map
  map = new google.maps.Map(document.getElementById('map'), options);

  // Listen for click and add marker 
  google.maps.event.addListener(map, 'click', function(event){
    // Add marker
    addMarker({coords:event.latLng});
  });



  /*
  // Add marker
  var marker = new google.maps.Marker({
    position:{lat:42.4668,lng:-70.9495},
    map:map,
    icon:'https://developers.google.com/maps/documentation/javascript/examples/full/images/beachflag.png'
  });

  var infoWindow = new google.maps.InfoWindow({
    content:'<h1>Lynn MA</h1>'
  });

  marker.addListener('click', function(){
    infoWindow.open(map, marker);
  });
  */

  // Array of markers
  markers = [
    {
      coords:{lat:42.4668,lng:-70.9495},
      iconImage:'https://developers.google.com/maps/documentation/javascript/examples/full/images/beachflag.png',
      content:'<h1>Lynn MA</h1>'
    },
    {
      coords:{lat:42.8584,lng:-70.9300},
      content:'<h1>Amesbury MA</h1>'
    },
    {
      coords:{lat:42.7762,lng:-71.0773}
    }
  ];

  // Loop through markers
  for(var i = 0;i < markers.length;i++){
    // Add marker
    addMarker(markers[i]);
  }

  // Add Marker Function
  function addMarker(props){
    var marker = new google.maps.Marker({
      position:props.coords,
      map:map,
      //icon:props.iconImage
    });

    // Check for customicon
    if(props.iconImage){
      // Set icon image
      marker.setIcon(props.iconImage);
    }

    // Check content
    if(props.content){
      var infoWindow = new google.maps.InfoWindow({
        content:props.content
      });

      marker.addListener('click', function(){
        infoWindow.open(map, marker);
      });
    }
  }

  const drawMgr = new google.maps.drawing.DrawingManager({
      drawingMode: google.maps.drawing.OverlayType.MARKET,
      drawingControl: true,
      drawingControlOptions: {
        position: google.maps.ControlPosition.TOP_CENTER,
        drawingModes: [
          google.maps.drawing.OverlayType.MARKER,
          google.maps.drawing.OverlayType.RECTANGLE,
          google.maps.drawing.OverlayType.POLYLINE,
        ],
      },
      polygonOptions: {editable: true}
  })
  
  drawMgr.setMap(map);

  google.maps.event.addListener(drawMgr, 'overlaycomplete', function(e) {
    all_overlays.push(e);
    if (e.type != google.maps.drawing.OverlayType.MARKER) {
      // Switch back to non-drawing mode after drawing a shape.


      // Add an event listener that selects the newly-drawn shape when the user
      // mouses down on it.
      var newShape = e.overlay;
      newShape.type = e.type;
      google.maps.event.addListener(newShape, 'click', function() {
        setSelection(newShape);
      });
      setSelection(newShape);
    }
  });
  // Switch back to non-drawing mode after drawing a shape.
  drawMgr.setDrawingMode(null);

  // Listen for click and add marker 
  google.maps.event.addListener(map, 'click', function(event){
  // Add marker
  addMarker({coords:event.latLng});
  });
  

  // Store map coordinates for polygons
  // read this for tomorrow https://stackoverflow.com/questions/32899213/getting-coordinates-of-rectangle-polygon-when-drawn-on-google-maps-with-drawing/32902755
  google.maps.event.addListener(drawMgr, 'overlaycomplete', function(overlay) {
  //alert("Created Box!");

    rectangle = overlay;

    var bounds = overlay.overlay.getBounds();
    var start = bounds.getNorthEast();
    var end = bounds.getSouthWest();

    const testcoordNE = start.toJSON(); 
    const testcoordSW = end.toJSON();
    const data = {testcoordNE, testcoordSW};
    
    console.log(test);

    var test = {'name': "jowi" }
    $.ajax({
      type: 'POST',
      url: "/geo/save",
      data: {
        //'data': JSON.stringify(data),
        'testcoordNE': testcoordNE,
        'testcoordSW': testcoordSW
      },
    })
  });
}

