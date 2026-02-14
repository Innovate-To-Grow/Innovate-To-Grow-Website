(function($) {

    Drupal.behaviors.open_framework = {
        attach: function(context, settings) {
            // Reset iPhone, iPad, and iPod zoom on orientation change to landscape
            var mobile_timer = false;
            if ((navigator.userAgent.match(/iPhone/i)) || (navigator.userAgent.match(/iPad/i)) || (navigator.userAgent.match(/iPod/i))) {
                $('#viewport').attr('content', 'width=device-width,minimum-scale=1.0,maximum-scale=1.0,initial-scale=1.0');
                $(window)
                    .bind('gesturestart', function() {
                        clearTimeout(mobile_timer);
                        $('#viewport').attr('content', 'width=device-width,minimum-scale=1.0,maximum-scale=10.0');
                    })
                    .bind('touchend', function() {
                        clearTimeout(mobile_timer);
                        mobile_timer = setTimeout(function() {
                            $('#viewport').attr('content', 'width=device-width,minimum-scale=1.0,maximum-scale=1.0,initial-scale=1.0');
                        }, 1000);
                    });
            }

            // Header Drupal Search Box
            $('#header [name=search_block_form]')
                .val('Search this site...')
                .focus(function() {
                    $(this).val('');
                });

            // Hide border for image links
            $('a:has(img)').css('border', 'none');

            // Apply the Equal Column Height function below by container
            // instead of page-wide
            equalHeightByContainer = function(className) {
                containerIDs = new Array();
                uncontainedExist = false;

                $(className).each(function() {
                    $el = $(this);
                    parentID = $el.offsetParent().attr('id');
                    if (typeof parentID !== 'undefined') {
                        if ($.inArray(parentID, containerIDs) === -1) {
                            containerIDs.push(parentID);
                        }
                    } else {
                        uncontainedExist = true;
                    }
                });

                if (uncontainedExist) {
                    equalHeight(className);
                }

                $.each(containerIDs, function() {
                    equalHeight('#' + this + ' ' + className);
                });
            }

            // Equal Column Height on load and resize
            // Credit: http://codepen.io/micahgodbolt/pen/FgqLc
            equalHeight = function(classname) {
                var currentTallest = 0,
                    currentRowStart = 0,
                    rowDivs = new Array(),
                    $el,
                    topPosition = 0;
                $(classname).each(function() {
                    $el = $(this);
                    $($el).height('auto')
                    topPosition = $el.position().top;

                    if (currentRowStart != topPosition) {
                        for (currentDiv = 0; currentDiv < rowDivs.length; currentDiv++) {
                            rowDivs[currentDiv].height(currentTallest);
                        }
                        rowDivs.length = 0; // empty the array
                        currentRowStart = topPosition;
                        currentTallest = $el.height();
                        rowDivs.push($el);
                    } else {
                        rowDivs.push($el);
                        currentTallest = (currentTallest < $el.height()) ? ($el.height()) : (currentTallest);
                    }
                    for (currentDiv = 0; currentDiv < rowDivs.length; currentDiv++) {
                        rowDivs[currentDiv].height(currentTallest);
                    }
                });
            }

            $(window).load(function() {
                equalHeightByContainer('.column');
            });

            $(window).resize(function() {
                equalHeightByContainer('.column');
            });


            // Add keyboard focus to .element-focusable elements in webkit browsers.
            $('.element-focusable').on('click', function() {
                $($(this).attr('href')).attr('tabindex', '-1').focus();
            });

            // Add placeholder value support for older browsers
            $('input, textarea').placeholder();

        }
    }

})(jQuery);

//Add legacy IE addEventListener support (http://msdn.microsoft.com/en-us/library/ms536343%28VS.85%29.aspx#1)
if (!window.addEventListener) {
    window.addEventListener = function(type, listener, useCapture) {
        attachEvent('on' + type, function() {
            listener(event)
        });
    }
}
//end legacy support addition

// Hide Address Bar in Mobile View
addEventListener("load", function() {
    setTimeout(hideURLbar, 0);
}, false);

function hideURLbar() {
    if (window.pageYOffset < 1) {
        window.scrollTo(0, 1);
    }
}
;
/*! http://mths.be/placeholder v1.8.7 by @mathias */
(function(f,h,c){var a='placeholder' in h.createElement('input'),d='placeholder' in h.createElement('textarea'),i=c.fn,j;if(a&&d){j=i.placeholder=function(){return this};j.input=j.textarea=true}else{j=i.placeholder=function(){return this.filter((a?'textarea':':input')+'[placeholder]').not('.placeholder').bind('focus.placeholder',b).bind('blur.placeholder',e).trigger('blur.placeholder').end()};j.input=a;j.textarea=d;c(function(){c(h).delegate('form','submit.placeholder',function(){var k=c('.placeholder',this).each(b);setTimeout(function(){k.each(e)},10)})});c(f).bind('unload.placeholder',function(){c('.placeholder').val('')})}function g(l){var k={},m=/^jQuery\d+$/;c.each(l.attributes,function(o,n){if(n.specified&&!m.test(n.name)){k[n.name]=n.value}});return k}function b(){var k=c(this);if(k.val()===k.attr('placeholder')&&k.hasClass('placeholder')){if(k.data('placeholder-password')){k.hide().next().show().focus().attr('id',k.removeAttr('id').data('placeholder-id'))}else{k.val('').removeClass('placeholder')}}}function e(){var o,n=c(this),k=n,m=this.id;if(n.val()===''){if(n.is(':password')){if(!n.data('placeholder-textinput')){try{o=n.clone().attr({type:'text'})}catch(l){o=c('<input>').attr(c.extend(g(this),{type:'text'}))}o.removeAttr('name').data('placeholder-password',true).data('placeholder-id',m).bind('focus.placeholder',b);n.data('placeholder-textinput',o).data('placeholder-id',m).before(o)}n=n.removeAttr('id').hide().prev().attr('id',m).show()}n.addClass('placeholder').val(n.attr('placeholder'))}else{n.removeClass('placeholder')}}}(this,document,jQuery));;
(function($) {

    Drupal.behaviors.open_framework_override = {
        attach: function(context, settings) {

            // Bootstrap dropdown menu in top nav bar
            // Bootstrap dropdown menu in secondary menu
            $('nav ul, #secondary-menu ul')
                .children('li')
                .filter(':has(.active)')
                .addClass('active')
                .end()
                .filter(':has(ul .active)')
                .removeClass('active')
                .end()
                .end()
                .find('ul a')
                .removeAttr('data-toggle')
                .removeAttr('data-target')

            // Bootstrap Menu Block behavior in sidebar
            $('.sidebar .block-menu-block ul.menu.nav a').removeAttr('data-toggle');
            $('.sidebar .block-menu-block ul.menu.nav a').removeAttr('data-target');
            $('.sidebar .block-menu-block ul.menu.nav li').removeClass('dropdown-submenu');
            $('.sidebar .block-menu-block ul.menu.nav ul').removeClass('dropdown-menu');

            // Set up theme specific responsive behaviors
            function responsive_behaviors() {
                var viewportwidth;
                var viewportheight;

                // the more standards compliant browsers (mozilla/netscape/opera/IE7) use window.innerWidth and window.innerHeight

                if (typeof window.innerWidth != 'undefined') {
                    viewportwidth = window.innerWidth,
                    viewportheight = window.innerHeight
                }

                // IE6 in standards compliant mode (i.e. with a valid doctype as the first line in the document)
                else if (typeof document.documentElement != 'undefined' && typeof document.documentElement.clientWidth !=
                    'undefined' && document.documentElement.clientWidth != 0) {
                    viewportwidth = document.documentElement.clientWidth,
                    viewportheight = document.documentElement.clientHeight
                }

                // older versions of IE
                else {
                    viewportwidth = document.getElementsByTagName('body')[0].clientWidth,
                    viewportheight = document.getElementsByTagName('body')[0].clientHeight
                }

                if (viewportwidth < 768) {
                    $('nav li li.expanded').removeClass('dropdown-submenu');
                    $('nav ul ul ul').removeClass('dropdown-menu');
                    $('div.next-row').addClass('clear-row');
                } else {
                    $('nav li li.expanded').addClass('dropdown-submenu');
                    $('nav ul ul ul').addClass('dropdown-menu');
                    $('div.next-row').removeClass('clear-row');
                }

                if ((viewportwidth >= 768) && (viewportwidth < 980)) {
                    $('.two-sidebars')
                        .find('.site-sidebar-first')
                        .removeClass('span3')
                        .addClass('span4')
                        .end()
                        .find('.site-sidebar-second')
                        .removeClass('span3')
                        .addClass('span12')
                        .end()
                        .find('.mc-content')
                        .removeClass('span6')
                        .addClass('span8')
                        .end()
                        .find('.region-sidebar-second .block')
                        .addClass('span4')
                        .end();
                    $('.sidebar-first')
                        .find('.site-sidebar-first')
                        .removeClass('span3')
                        .addClass('span4')
                        .end()
                        .find('.mc-content')
                        .removeClass('span9')
                        .addClass('span8')
                        .end();
                    $('.sidebar-second')
                        .find('.site-sidebar-second')
                        .removeClass('span3')
                        .addClass('span12')
                        .end()
                        .find('.mc-content')
                        .removeClass('span9')
                        .addClass('span12')
                        .end()
                        .find('.region-sidebar-second .block')
                        .addClass('span4')
                        .end();
                } else {
                    $('.two-sidebars')
                        .find('.site-sidebar-first')
                        .removeClass('span4')
                        .addClass('span3')
                        .end()
                        .find('.site-sidebar-second')
                        .removeClass('span12')
                        .addClass('span3')
                        .end()
                        .find('.mc-content')
                        .removeClass('span8')
                        .addClass('span6')
                        .end()
                        .find('.region-sidebar-second .block')
                        .removeClass('span4')
                        .end();
                    $('.sidebar-first')
                        .find('.site-sidebar-first')
                        .removeClass('span4')
                        .addClass('span3')
                        .end()
                        .find('.mc-content')
                        .removeClass('span8')
                        .addClass('span9')
                        .end();
                    $('.sidebar-second')
                        .find('.site-sidebar-second')
                        .removeClass('span12')
                        .addClass('span3')
                        .end()
                        .find('.mc-content')
                        .removeClass('span12')
                        .addClass('span9')
                        .end()
                        .find('.region-sidebar-second .block')
                        .removeClass('span4')
                        .end();
                }
            }

            // Update CSS classes based on window load and resize
            $(window)
                .load(responsive_behaviors)
                .resize(responsive_behaviors);
        }
    }

})(jQuery);
;
/*! Respond.js v1.4.0: min/max-width media query polyfill. (c) Scott Jehl. MIT Lic. j.mp/respondjs  */

window.onpageshow = function(event) {
  if (event.persisted) {
    window.location.reload()
  }
};

(function( w ){

	"use strict";

	//exposed namespace
	var respond = {};
	w.respond = respond;

	//define update even in native-mq-supporting browsers, to avoid errors
	respond.update = function(){};

	//define ajax obj
	var requestQueue = [],
		xmlHttp = (function() {
			var xmlhttpmethod = false;
			try {
				xmlhttpmethod = new w.XMLHttpRequest();
			}
			catch( e ){
				xmlhttpmethod = new w.ActiveXObject( "Microsoft.XMLHTTP" );
			}
			return function(){
				return xmlhttpmethod;
			};
		})(),

		//tweaked Ajax functions from Quirksmode
		ajax = function( url, callback ) {
			var req = xmlHttp();
			if (!req){
				return;
			}
			req.open( "GET", url, true );
			req.onreadystatechange = function () {
				if ( req.readyState !== 4 || req.status !== 200 && req.status !== 304 ){
					return;
				}
				callback( req.responseText );
			};
			if ( req.readyState === 4 ){
				return;
			}
			req.send( null );
		};

	//expose for testing
	respond.ajax = ajax;
	respond.queue = requestQueue;

	// expose for testing
	respond.regex = {
		media: /@media[^\{]+\{([^\{\}]*\{[^\}\{]*\})+/gi,
		keyframes: /@(?:\-(?:o|moz|webkit)\-)?keyframes[^\{]+\{(?:[^\{\}]*\{[^\}\{]*\})+[^\}]*\}/gi,
		urls: /(url\()['"]?([^\/\)'"][^:\)'"]+)['"]?(\))/g,
		findStyles: /@media *([^\{]+)\{([\S\s]+?)$/,
		only: /(only\s+)?([a-zA-Z]+)\s?/,
		minw: /\([\s]*min\-width\s*:[\s]*([\s]*[0-9\.]+)(px|em)[\s]*\)/,
		maxw: /\([\s]*max\-width\s*:[\s]*([\s]*[0-9\.]+)(px|em)[\s]*\)/
	};

	//expose media query support flag for external use
	respond.mediaQueriesSupported = w.matchMedia && w.matchMedia( "only all" ) !== null && w.matchMedia( "only all" ).matches;

	//if media queries are supported, exit here
	if( respond.mediaQueriesSupported ){
		return;
	}

	//define vars
	var doc = w.document,
		docElem = doc.documentElement,
		mediastyles = [],
		rules = [],
		appendedEls = [],
		parsedSheets = {},
		resizeThrottle = 30,
		head = doc.getElementsByTagName( "head" )[0] || docElem,
		base = doc.getElementsByTagName( "base" )[0],
		links = head.getElementsByTagName( "link" ),

		lastCall,
		resizeDefer,

		//cached container for 1em value, populated the first time it's needed
		eminpx,

		// returns the value of 1em in pixels
		getEmValue = function() {
			var ret,
				div = doc.createElement('div'),
				body = doc.body,
				originalHTMLFontSize = docElem.style.fontSize,
				originalBodyFontSize = body && body.style.fontSize,
				fakeUsed = false;

			div.style.cssText = "position:absolute;font-size:1em;width:1em";

			if( !body ){
				body = fakeUsed = doc.createElement( "body" );
				body.style.background = "none";
			}

			// 1em in a media query is the value of the default font size of the browser
			// reset docElem and body to ensure the correct value is returned
			docElem.style.fontSize = "100%";
			body.style.fontSize = "100%";

			body.appendChild( div );

			if( fakeUsed ){
				docElem.insertBefore( body, docElem.firstChild );
			}

			ret = div.offsetWidth;

			if( fakeUsed ){
				docElem.removeChild( body );
			}
			else {
				body.removeChild( div );
			}

			// restore the original values
			docElem.style.fontSize = originalHTMLFontSize;
			if( originalBodyFontSize ) {
				body.style.fontSize = originalBodyFontSize;
			}


			//also update eminpx before returning
			ret = eminpx = parseFloat(ret);

			return ret;
		},

		//enable/disable styles
		applyMedia = function( fromResize ){
			var name = "clientWidth",
				docElemProp = docElem[ name ],
				currWidth = doc.compatMode === "CSS1Compat" && docElemProp || doc.body[ name ] || docElemProp,
				styleBlocks	= {},
				lastLink = links[ links.length-1 ],
				now = (new Date()).getTime();

			//throttle resize calls
			if( fromResize && lastCall && now - lastCall < resizeThrottle ){
				w.clearTimeout( resizeDefer );
				resizeDefer = w.setTimeout( applyMedia, resizeThrottle );
				return;
			}
			else {
				lastCall = now;
			}

			for( var i in mediastyles ){
				if( mediastyles.hasOwnProperty( i ) ){
					var thisstyle = mediastyles[ i ],
						min = thisstyle.minw,
						max = thisstyle.maxw,
						minnull = min === null,
						maxnull = max === null,
						em = "em";

					if( !!min ){
						min = parseFloat( min ) * ( min.indexOf( em ) > -1 ? ( eminpx || getEmValue() ) : 1 );
					}
					if( !!max ){
						max = parseFloat( max ) * ( max.indexOf( em ) > -1 ? ( eminpx || getEmValue() ) : 1 );
					}

					// if there's no media query at all (the () part), or min or max is not null, and if either is present, they're true
					if( !thisstyle.hasquery || ( !minnull || !maxnull ) && ( minnull || currWidth >= min ) && ( maxnull || currWidth <= max ) ){
						if( !styleBlocks[ thisstyle.media ] ){
							styleBlocks[ thisstyle.media ] = [];
						}
						styleBlocks[ thisstyle.media ].push( rules[ thisstyle.rules ] );
					}
				}
			}

			//remove any existing respond style element(s)
			for( var j in appendedEls ){
				if( appendedEls.hasOwnProperty( j ) ){
					if( appendedEls[ j ] && appendedEls[ j ].parentNode === head ){
						head.removeChild( appendedEls[ j ] );
					}
				}
			}
			appendedEls.length = 0;

			//inject active styles, grouped by media type
			for( var k in styleBlocks ){
				if( styleBlocks.hasOwnProperty( k ) ){
					var ss = doc.createElement( "style" ),
						css = styleBlocks[ k ].join( "\n" );

					ss.type = "text/css";
					ss.media = k;

					//originally, ss was appended to a documentFragment and sheets were appended in bulk.
					//this caused crashes in IE in a number of circumstances, such as when the HTML element had a bg image set, so appending beforehand seems best. Thanks to @dvelyk for the initial research on this one!
					head.insertBefore( ss, lastLink.nextSibling );

					if ( ss.styleSheet ){
						ss.styleSheet.cssText = css;
					}
					else {
						ss.appendChild( doc.createTextNode( css ) );
					}

					//push to appendedEls to track for later removal
					appendedEls.push( ss );
				}
			}
		},
		//find media blocks in css text, convert to style blocks
		translate = function( styles, href, media ){
			var qs = styles.replace( respond.regex.keyframes, '' ).match( respond.regex.media ),
				ql = qs && qs.length || 0;

			//try to get CSS path
			href = href.substring( 0, href.lastIndexOf( "/" ) );

			var repUrls = function( css ){
					return css.replace( respond.regex.urls, "$1" + href + "$2$3" );
				},
				useMedia = !ql && media;

			//if path exists, tack on trailing slash
			if( href.length ){ href += "/"; }

			//if no internal queries exist, but media attr does, use that
			//note: this currently lacks support for situations where a media attr is specified on a link AND
				//its associated stylesheet has internal CSS media queries.
				//In those cases, the media attribute will currently be ignored.
			if( useMedia ){
				ql = 1;
			}

			for( var i = 0; i < ql; i++ ){
				var fullq, thisq, eachq, eql;

				//media attr
				if( useMedia ){
					fullq = media;
					rules.push( repUrls( styles ) );
				}
				//parse for styles
				else{
					fullq = qs[ i ].match( respond.regex.findStyles ) && RegExp.$1;
					rules.push( RegExp.$2 && repUrls( RegExp.$2 ) );
				}

				eachq = fullq.split( "," );
				eql = eachq.length;

				for( var j = 0; j < eql; j++ ){
					thisq = eachq[ j ];
					mediastyles.push( {
						media : thisq.split( "(" )[ 0 ].match( respond.regex.only ) && RegExp.$2 || "all",
						rules : rules.length - 1,
						hasquery : thisq.indexOf("(") > -1,
						minw : thisq.match( respond.regex.minw ) && parseFloat( RegExp.$1 ) + ( RegExp.$2 || "" ),
						maxw : thisq.match( respond.regex.maxw ) && parseFloat( RegExp.$1 ) + ( RegExp.$2 || "" )
					} );
				}
			}

			applyMedia();
		},

		//recurse through request queue, get css text
		makeRequests = function(){
			if( requestQueue.length ){
				var thisRequest = requestQueue.shift();

				ajax( thisRequest.href, function( styles ){
					translate( styles, thisRequest.href, thisRequest.media );
					parsedSheets[ thisRequest.href ] = true;

					// by wrapping recursive function call in setTimeout
					// we prevent "Stack overflow" error in IE7
					w.setTimeout(function(){ makeRequests(); },0);
				} );
			}
		},

		//loop stylesheets, send text content to translate
		ripCSS = function(){

			for( var i = 0; i < links.length; i++ ){
				var sheet = links[ i ],
				href = sheet.href,
				media = sheet.media,
				isCSS = sheet.rel && sheet.rel.toLowerCase() === "stylesheet";

				//only links plz and prevent re-parsing
				if( !!href && isCSS && !parsedSheets[ href ] ){
					// selectivizr exposes css through the rawCssText expando
					if (sheet.styleSheet && sheet.styleSheet.rawCssText) {
						translate( sheet.styleSheet.rawCssText, href, media );
						parsedSheets[ href ] = true;
					} else {
						if( (!/^([a-zA-Z:]*\/\/)/.test( href ) && !base) ||
							href.replace( RegExp.$1, "" ).split( "/" )[0] === w.location.host ){
							// IE7 doesn't handle urls that start with '//' for ajax request
							// manually add in the protocol
							if ( href.substring(0,2) === "//" ) { href = w.location.protocol + href; }
							requestQueue.push( {
								href: href,
								media: media
							} );
						}
					}
				}
			}
			makeRequests();
		};

	//translate CSS
	ripCSS();

	//expose update for re-running respond later on
	respond.update = ripCSS;

	//expose getEmValue
	respond.getEmValue = getEmValue;

	//adjust on resize
	function callMedia(){
		applyMedia( true );
	}

	if( w.addEventListener ){
		w.addEventListener( "resize", callMedia, false );
	}
	else if( w.attachEvent ){
		w.attachEvent( "onresize", callMedia );
	}
})(this);

// v3.1.0
//Docs at http://simpleweatherjs.com
// (function($) {
// 	"use strict";

// 	$(document).ready(function() {
// 		var weatherDOM = "";
// 		$.simpleWeather({
//             location: "Merced, CA",
// 			woeid: "",
// 			unit: "f",
// 			success: function(weather) {
// 				if (typeof weather !== "undefined") {
//                     weatherDOM = '<span><i class="icon-'+weather.code+'"></i> '+weather.temp+'&deg;'+weather.units.temp+'</span>';
//                     // html += '<ul><li>'+weather.city+', '+weather.region+'</li>';
//                     // html += '<li class="currently">'+weather.currently+'</li>';
//                     // html += '<li>'+weather.wind.direction+' '+weather.wind.speed+' '+weather.units.speed+'</li></ul>';

//                     $("#weather").html(weatherDOM);
// 				}
// 			},
// 			error: function(error) {
// 				// $("#weather").html("<p>"+error+"</p>");
//                 $("#weather").html("<span class='no-weather'></span>");
// 			}
// 		});
//         // .setTimeout(function () {
// 			// $("#weather").html("<span class='no-weather'></span>");
//         // }, 2000);
// 	});
// })(jQuery);

(function($) {

	$(".main-menu li").on('mouseenter mouseleave', function (e) {
		if ($('ul', this).length) {
			var elm = $('ul:first', this);
			var off = elm.offset();
			var l = off.left;
			var w = elm.width();
			var docH = $(window).height();
			var docW = $(".container").width();
			var isEntirelyVisible = (w <= docW);
            // alert(isEntirelyVisible);

			if (!isEntirelyVisible) {
				$(this).addClass('edge');
			} else {
				$(this).removeClass('edge');
			}
		}
	});

	// $(window).bind("pageshow", function(event) {
	// 	if (event.originalEvent.persisted) {
	// 		window.location.reload()
	// 	}
	// });

})(jQuery);

;
