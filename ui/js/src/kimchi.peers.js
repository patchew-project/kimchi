/*
 * Project Kimchi
 *
 * Copyright IBM Corp, 2013-2016
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

kimchi.initPeers = function() {

    var peersDatatableTable;
    var peers = new Array();

    var peersAccordion = wok.substitute($('#peersPanel').html());
    $('#peers-container > div').append(peersAccordion);

    var peersDatatable = function(nwConfigDataSet) {
        peersDatatableTable = $('#peers-list').DataTable({
            "processing": true,
            "data": peers,
            "language": {
                "emptyTable": i18n['WOKSETT0010M']
            },
            "order": [],
            "paging": false,
            "dom": '<"row"<"col-sm-12"t>>',
            "scrollY": "269px",
            "scrollCollapse": true,
            "columnDefs": [{
                "targets": 0,
                "searchable": false,
                "orderable": false,
                "width": "100%",
                "className": "tabular-data",
                "render": function(data, type, full, meta) {
                    return '<a href="' + data + '" target="_blank">' + data + '</a>';
                }
            }],
            "initComplete": function(settings, json) {
                $('#peers-content-area > .wok-mask').addClass('hidden');
            }
        });
    };

    var getPeers = function() {
        kimchi.getPeers(function(result) {
            peers.length = 0;
            for (var i = 0; i < result.length; i++) {
                var tempArr = [];
                tempArr.push(result[i]);
                peers.push(tempArr);
            }
            peersDatatable(peers);
        }, function(err) {
            wok.message.error(err.responseJSON.reason, '#peers-alert-container', true);
        });
    };

    kimchi.listPeers = getPeers();

}
