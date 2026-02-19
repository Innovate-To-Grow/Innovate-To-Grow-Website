(function ($) {
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const d = new Date();
  let month = months[d.getMonth()];
  let weekday = days[d.getDay()];
  let day = d.getDate();
  let year = d.getFullYear();
  let date = weekday + ' ' + day + ' ' + month + ' ' + year;
  $('#today').append(date);

  Drupal.behaviors.fancyFileDeleteViewRefresh = {
    attach: function() {
      // Refresh the view
      $('.ffd-refresh').click( function() {
        $('.view-id-fancy_file_list_unmanaged').trigger('RefreshView');
      });
    }
  }
})(jQuery);
;



// Monday 10 August 2020

