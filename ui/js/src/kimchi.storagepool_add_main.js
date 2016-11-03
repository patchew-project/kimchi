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

kimchi.storagepool_add_main = function() {
    kimchi.initStorageAddPage();
    sessionStorage.clear();
    $('#form-pool-add').on('submit', kimchi.addPool);
    $('#pool-doAdd').on('click', kimchi.addPool);
    // 'pool-doAdd' button starts as disabled.
    $("#pool-doAdd").attr("disabled", true);
    // Make any change in the form fields enables the
    // 'pool-doAdd' button if all the visible form
    // fields are filled, disables it otherwise.
    $('#form-pool-add').on('input change propertychange', function() {
        if (!kimchi.inputsNotBlank()){
                    $("#pool-doAdd").attr("disabled", true);
        }
        else {
           $("#pool-doAdd").attr("disabled", false);
        }
    });
};

kimchi.storageFilterSelect = function(id, isUpdate) {
    var input = $('input', '#'+id);
    var options = $(".option", '#'+id);
    var filter = function(container, key){
        container.children().each(function(){
            $(this).css("display", $(this).text().indexOf(key)===-1 ? "none" : "");
        });
    };
    if(!isUpdate){
        input.on("keyup", function(){
            filter(options, input.val());
        });
    }
    options.children().each(function(){
        $(this).click(function(){
            options.children().removeClass("active");
            input.val($(this).text());
            input.trigger("change");
            $(this).addClass("active");
            filter(options, "");
        });
    });
};

kimchi.setupISCSI = function(){
    var loadTargets = function(server, port, callback){
        var isUpdate = $(".option", "#iSCSITarget").children().length > 0;
        $(".option", "#iSCSITarget").empty();
        $('input', "#iSCSITarget").attr("placeholder", i18n['KCHPOOL6006M']);
        kimchi.getISCSITargets(server, port, function(data){
            if(data.length===0){
                $('input', "#iSCSITarget").attr("placeholder", i18n['KCHPOOL6007M']);
            }else{
                for(var i=0; i<data.length; i++){
                    var itemNode = $.parseHTML("<li>"+data[i].target+"</li>");
                    $(".option", "#iSCSITarget").append(itemNode);
                }
                $('input', "#iSCSITarget").attr("placeholder", "");
                $(".popover", "#iSCSITarget").css("display", "block");
            }
            kimchi.storageFilterSelect('iSCSITarget', isUpdate);
            $('input', "#iSCSITarget").trigger("focus");
            callback();
        }, function(data){
            $('input', "#iSCSITarget").attr("placeholder", i18n['KCHPOOL6008M']);
            callback();
            wok.message.error(data.responseJSON.reason,'#alert-modal-container');
        });
    };
    var triggerLoadTarget = function(){
        $('input', "#iSCSITarget").val("");
        var server = $("#iscsiserverId").val().trim();
        var port = $("#iscsiportId").val().trim();
        if(server!=="" && !$("#iscsiserverId").hasClass("invalid-field") && !$("#iscsiportId").hasClass("invalid-field")){
            $("#iscsiserverId").attr("disabled", true);
            $("#iscsiportId").attr("disabled", true);
            loadTargets(server, port, function(){
                $("#iscsiserverId").attr("disabled", false);
                $("#iscsiportId").attr("disabled", false);
            });
        }
    };
    $("#iscsiserverId").change(function(){
        $('input', "#iSCSITarget").off('focus', triggerLoadTarget);
        $('input', "#iSCSITarget").one('focus', triggerLoadTarget);
    });
    $("#iscsiportId").change(function(){
        $('input', "#iSCSITarget").off('focus', triggerLoadTarget);
        $('input', "#iSCSITarget").one('focus', triggerLoadTarget);
    });
    var initISCSIServers = function(){
        kimchi.getStorageServers("iscsi", function(data){
            for(var i=0;i<data.length;i++){
                var itemNode = $.parseHTML("<li>"+data[i].host+"</li>");
                $(".option", "#iSCSIServer").append(itemNode);
                $(itemNode).click(function(){
                    $("#iscsiportId").val($(this).prop("port"));
                    $("#iscsiserverId").val($(this).text());
                    triggerLoadTarget();
                }).prop("port", data[i].port);
            }
            kimchi.storageFilterSelect('iSCSIServer', false);
         });
    };
    initISCSIServers();
};

kimchi.initStorageAddPage = function() {
    kimchi.listHostPartitions(function(data) {
        if (data.length > 0) {
            var deviceHtml = $('#partitionTmpl').html();
            var listHtml = '<table class="table table-hover"><thead><tr><th></th><th>'+i18n['KCHPOOL6025M']+'</th><th>'+i18n['KCHPOOL6026M']+'</th><th>'+i18n['KCHPOOL6027M']+'</th></tr></thead><tbody>';
            valid_types = ['part', 'disk', 'mpath'];
            $.each(data, function(index, value) {
                if (valid_types.indexOf(value.type) !== -1) {
                    value.size = (value.size / 1000000000).toFixed(2);
                    listHtml += wok.substitute(deviceHtml, value);
                }
            });
            listHtml += '</tbody></table>';
            $('.host-partition', '#form-pool-add').html(listHtml);
        } else {
            $('.host-partition').html(i18n['KCHPOOL6011M']);
            $('.host-partition').addClass('text-help');
        }
    }, function(err) {
        $('.host-partition').html(i18n['KCHPOOL6013M'] + '<br/>(' + err.responseJSON.reason + ')');
        $('.host-partition').addClass('text-help');
    });

    kimchi.getHostVgs(function(data){
        if (data.length > 0) {
            var deviceHtml = $('#existingLvmTmpl').html();
            var listHtml = '<table class="table table-hover"><thead><tr><th></th><th>'+i18n['KCHPOOL6025M']+'</th><th>'+i18n['KCHPOOL6027M']+'</th><th>'+i18n['KCHPOOL6028M']+'</th></tr></thead><tbody>';
            $.each(data, function(index, value) {
                value.size = (value.size / 1000000000).toFixed(2);
                value.free = (value.free / 1000000000).toFixed(2);
                listHtml += wok.substitute(deviceHtml, value);
            });
            listHtml += '</tbody></table>';
            $('.lvm-partition').html(listHtml);
        } else {
            $('.lvm-partition').html(i18n['KCHPOOL6016M']);
            $('.lvm-partition').addClass('text-help');
        }
    }, function(err) {
        $('.lvm-partition').html(i18n['KCHPOOL6013M'] + '<br/>(' + err.responseJSON.reason + ')');
        $('.lvm-partition').addClass('text-help');
    });

    kimchi.getHostFCDevices(function(data){
        $scsiSelect = $('#scsiAdapter');
        if(data.length>0){
            for(var i=0;i<data.length;i++){
                data[i].label = data[i].name;
                data[i].value = data[i].name;
            }
            //$('#scsiAdapter').selectMenu();
            var scsiOptionHtml = '';
            for (var i=0;i<data.length;i++){
              scsiOptionHtml += '<option value="'+ data[i].value + '">' + data[i].label + '</option>';
            }
            $scsiSelect.append(scsiOptionHtml);
            $scsiSelect.selectpicker();
        } else {
            $scsiSelect.remove();
            $('.scsi-adapters-list').html(i18n['KCHPOOL6005M']);
            $('.scsi-adapters-list').addClass('text-help');
        }
    });

    $('#serverComboboxId').combobox();
    $('#targetFilterSelectId').filterselect();
    var options = [ {
        label : i18n.KCHPOOL6021M,
        value : "dir"
    }, {
        label : i18n.KCHPOOL6022M,
        value : "netfs"
    }, {
        label : i18n.KCHPOOL6023M,
        value : "iscsi"
    }, {
        label : i18n.KCHPOOL6024M,
        value : "logical"
    }, {
        label : i18n.KCHPOOL6004M,
        value : "scsi"
    } ];
    var $select = $('#poolTypeInputId');
    var optionHtml = '';
    for (var i=0;i<options.length;i++){
      optionHtml += '<option value="'+ options[i].value + '">' + options[i].label + '</option>';
    }
    $select.append(optionHtml);
    $select.selectpicker();

    kimchi.getStorageServers('netfs', function(data) {
        var serverContent = [];
        if (data.length > 0) {
            $.each(data, function(index, value) {
                serverContent.push({
                    label : value.host,
                    value : value.host
                });
            });
            $('#serverComboboxId').combobox("setData", serverContent);
        }else {
            $('#serverComboboxId').combobox("destroy");
        }

        $('input[name=nfsServerType]').change(function() {
            if ($(this).val() === 'input') {
                $('#nfsServerInputDiv').removeClass('tmpl-html');
                $('#nfsServerChooseDiv').addClass('tmpl-html');
            } else {
                $('#nfsServerInputDiv').addClass('tmpl-html');
                $('#nfsServerChooseDiv').removeClass('tmpl-html');
            }
        });
        $('#nfsserverId').on("change keyup",function() {
            if ($(this).val() !== '' && wok.isServer($(this).val())) {
                $('#nfspathId').prop('disabled',false);
                $(this).removeClass("invalid-field");
            } else {
                $(this).addClass("invalid-field");
                $('#nfspathId').prop( "disabled",true);
            }
            $('#targetFilterSelectId').filterselect('clear');
        });
        $('#nfspathId').focus(function() {
            var targetContent = [];
            kimchi.getStorageTargets($('#nfsserverId').val(), 'netfs', function(data) {
                if (data.length > 0) {
                    $.each(data, function(index, value) {
                        targetContent.push({
                            label : value.target,
                            value : value.target
                        });
                    });
                    $('#targetFilterSelectId').filterselect("setData", targetContent);
                }else {
                    $('#targetFilterSelectId').filterselect('destroy');
                }
            });
        });
    });

    $('#poolTypeInputId').change(function() {

        kimchi.cleanLogicalForm();
        $('#poolId').css("background-color", "#ffffff").attr('readonly', false);
        $('[name="logicalRadioSelection"]')[1].checked = true;
        $('.lvm-group').addClass('hidden');
        $('.disk-group').removeClass('hidden');
        kimchi.setOldStorageName();

        var poolObject = {'dir': ".path-section", 'netfs': '.nfs-section',
                          'iscsi': '.iscsi-section', 'scsi': '.scsi-section',
                          'logical': '.logical-section'};
        var selectType = $(this).val();
        $.each(poolObject, function(type, value) {
            if(selectType === type){
                $(value).removeClass('hidden');
            } else {
                $(value).addClass('hidden');
            }
        });
    });
    $('#authId').click(function() {
        if ($(this).prop("checked")) {
            $('.authenticationfield').removeClass('hidden');
        } else {
            $('.authenticationfield').addClass('hidden');
        }
    });
    $('#iscsiportId').keyup(function(event) {
        $(this).toggleClass("invalid-field",!/^[0-9]*$/.test($(this).val()));
    });
    $('#iscsiserverId').keyup(function(event) {
        $(this).toggleClass("invalid-field",!wok.isServer($(this).val().trim()));
    }).change(function(event) {
        $(this).toggleClass("invalid-field",!wok.isServer($(this).val().trim()));
    });

    $('[name="logicalRadioSelection"]').change(function(){
        kimchi.cleanLogicalForm();
        kimchi.setOldStorageName();
        var selectedRadio = ($(this).val());
        var logicalObject = {'existingLvm' : '.lvm-group', 'rawDisk' : '.disk-group'};

        if(selectedRadio === 'existingLvm') {
            $('[name="lvmTmplRadioSelection"]').change(function(){
                $('#poolId').css("background-color", "#EEE").val($(this).val()).attr('readonly', true);
            });
        } else {
            $('#poolId').css("background-color", "#ffffff").attr('readonly', false);
        }

        $.each(logicalObject, function(type, value) {
            if(selectedRadio === type){
                $(value).removeClass('hidden');
            } else {
                $(value).addClass('hidden');
            }
        });
    });

    $('#poolId').blur(function() {
        sessionStorage.setItem('oldStorageName', $('#poolId').val());
    })

    kimchi.setupISCSI();
};

kimchi.setOldStorageName = function() {
    if(sessionStorage.getItem('oldStorageName') !== ''){
        $('#poolId').val(sessionStorage.getItem('oldStorageName'));
    } else {
        $('#poolId').val('');
    }
}

kimchi.cleanLogicalForm = function() {
    $("input[name=devices]").attr('checked', false);
    $("input[name=lvmTmplRadioSelection]").attr('checked', false);
}

/* Returns 'true' if all form fields were filled, 'false' if
 * any field is left blank. The function takes into account
 * the current poolType selected.
 *
 * Any 'field is blank' verification that were done in other
 * validate functions were deleted, since we're doing it here
 * already.
 */
kimchi.inputsNotBlank = function() {
    if (!$('#poolId').val()) { return false; }
    var poolType = $("#poolTypeInputId").val();
    if (poolType === "dir") {
        if (!$('#pathId').val()) { return false; }
    } else if (poolType === "netfs") {
        if (!$('#nfspathId').val()) { return false; }
        if (!$('#nfsserverId').val()) { return false; }
    } else if (poolType === "iscsi") {
        if (!$('#iscsiserverId').val()) { return false; }
        if (!$('#iscsiTargetId').val()) { return false; }
    } else if (poolType === "logical") {
        if ($("input[name=devices]:checked").length === 0 && $("input[name=lvmTmplRadioSelection]:checked").length === 0){
                    return false;
            }
    }
    return true;
};

kimchi.validateForm = function() {
    var poolType = $("#poolTypeInputId").val();
    if (poolType === "dir") {
        return kimchi.validateDirForm();
    } else if (poolType === "netfs") {
        return kimchi.validateNfsForm();
    } else if (poolType === "iscsi") {
        return kimchi.validateIscsiForm();
    } else if (poolType === "logical") {
        return kimchi.validateLogicalForm();
    } else {
        return true;
    }
};

kimchi.validateDirForm = function () {
    var path = $('#pathId').val();
    if (!/(^\/.*)$/.test(path)) {
        wok.message.error.code('KCHAPI6003E','#alert-modal-container');
        return false;
    }
    return true;
};

kimchi.validateNfsForm = function () {
    var nfspath = $('#nfspathId').val();
    var nfsserver = $('#nfsserverId').val();
    if (!kimchi.validateServer(nfsserver)) {
        return false;
    }
    if (!/((\/([0-9a-zA-Z-_\.]+)))$/.test(nfspath)) {
        wok.message.error.code('KCHPOOL6005E','#alert-modal-container');
        return false;
    }
    $('#nfs-mount-loading').removeClass('hidden');
    return true;
};

kimchi.validateIscsiForm = function() {
    var iscsiServer = $('#iscsiserverId').val();
    var iscsiTarget = $('#iscsiTargetId').val();
    if (!kimchi.validateServer(iscsiServer)) {
        return false;
    }
    return true;
};

kimchi.validateServer = function(serverField) {
    if(!wok.isServer(serverField)) {
        wok.message.error.code('KCHPOOL6009E','#alert-modal-container');
        return false;
    }
    return true;
};

kimchi.validateLogicalForm = function () {
    if ($("input[name=devices]:checked").length === 0 && $("input[name=lvmTmplRadioSelection]:checked").length === 0) {
        wok.message.error.code('KCHPOOL6006E','#alert-modal-container');
        return false;
    } else {
        return true;
    }
};

kimchi.addPool = function(event) {
    if (kimchi.validateForm()) {
        var formData = $('#form-pool-add').serializeObject();
        delete formData.authname;
        delete formData.logicalRadioSelection;
        delete formData.lvmTmplRadioSelection;
        var poolType = $('#poolTypeInputId').val();
        formData.type = poolType;
        if (poolType === 'dir') {
            formData.path = $('#pathId').val();
        } else if (poolType === 'logical') {
            var logicalrRadioSelected = $("input[name='logicalRadioSelection']:checked").val();
            var source = {};
            if (logicalrRadioSelected === 'rawDisk') {
                if (!$.isArray(formData.devices)) {
                    var deviceObj = [];
                    deviceObj[0] =  formData.devices;
                    source.devices = deviceObj;
                } else {
                    source.devices = formData.devices;
                }
                delete formData.devices;
            } else if (logicalrRadioSelected === 'existingLvm') {
                source.from_vg = true;
            }
            formData.source = source;
        } else if (poolType === 'netfs'){
            var source = {};
            source.path = $('#nfspathId').val();
            source.host = $('#nfsserverId').val();
            formData.source = source;
        } else if (poolType === 'iscsi') {
            var source = {};
            source.target = $('#iscsiTargetId').val();
            source.host = $('#iscsiserverId').val();
            $('#iscsiportId').val() !== '' ? source.port = parseInt($('#iscsiportId').val()): null;
            if ($('#authId').prop("checked")) {
                source.auth = {
                    "username" : $('#usernameId').val(),
                    "password" : $('#passwordId').val()
                };
            }
            formData.source = source;
        } else if (poolType === 'scsi'){
            formData.source = { adapter_name: $('#scsiAdapter').val() };
        }
        var storagePoolAddingFunc = function() {
            $('input', '#form-pool-add').attr('disabled','disabled');
            $('#pool-doAdd').hide();
            $('#pool-loading').show();
            kimchi.createStoragePool(formData, function() {
                    kimchi.doListStoragePools();
                    wok.window.close();
                }, function(err) {
                    wok.message.error(err.responseJSON.reason,'#alert-modal-container');
                    $('input', '#form-pool-add').removeAttr('disabled');
                    $('#pool-loading').hide();
                    $('#pool-doAdd').show();
                });
        };
        if (poolType === 'logical' && $("input[name='logicalRadioSelection']:checked").val() === 'rawDisk') {
            var settings = {
                title : i18n['KCHAPI6001M'],
                content : i18n['KCHPOOL6003M'],
                confirm : i18n['KCHAPI6002M'],
                cancel : i18n['KCHAPI6003M']
            };
            wok.confirm(settings, function() {
                storagePoolAddingFunc();
            }, function() {
            });
        } else {
            storagePoolAddingFunc();
        }
    }
};
