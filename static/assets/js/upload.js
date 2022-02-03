//Used for tourney dropdown selection to change the tourney/subtourney fields
function changeTourneyDropdown(src) {
    //Get value holding elements
    var tourneyTxt = document.getElementById("currentTourney")
    var subTourneyTxt = document.getElementById("currentSubTourney")

    //Get the input elements
    var tourneyInput = document.getElementById("tourneyInput")
    var subTourneyInput = document.getElementById("subTourneyInput")

    //If no tourney selected
    if (src.id == "noTourney") {
        tourneyTxt.value = "Tournament: None"
        subTourneyTxt.value = "Sub-Tournament: None"

        tourneyInput.value = "None"
        subTourneyInput.value = "None"
    
    //If tourney selected
    } else {
        tourney = src.parentNode.parentNode.parentNode.children[0].innerHTML
        subTourney = src.innerHTML
        if (subTourney == 'No Sub-Tournament') {
            subTourney = "None"
        }
        tourneyTxt.value = "Tournament: " + tourney
        subTourneyTxt.value = "Sub-Tournament: " + subTourney

        tourneyInput.value = tourney
        subTourneyInput.value = subTourney
    }
}

//Creates a new subtourney for specified tournament
function createNewSubTourney() {
    //Get the new sub tourney value and other necessary elements
    var newSubTourney = document.getElementById("newSubTourney").value
    var selectedTourney = document.getElementById("currentTourney").value.substring(12)

    //Get error div and style
    var errorDiv = document.getElementById("newSubTWarning")
    errorDiv.style.color = 'rgba(244, 113, 116, 1.0)';
    errorDiv.style.textAlign = "center";

    //Verify contents
    if (!newSubTourney) {
        errorDiv.innerHTML = "Please fill out the new sub-tournament field";
        return;
      } else if (newSubTourney.includes("_") || newSubTourney.includes(",") || newSubTourney.includes("|") || newSubTourney.includes("<") || newSubTourney.includes(">")) {
        errorDiv.innerHTML = "Sorry, the underscore (_), comma (,), pipe (|), and chevron (<>) characters are not allowed";
        return;
      } else if (newSubTourney.length > 64) {
        errorDiv.innerHTML = "Sorry, maximum of 64 characters";
        return;
      } else if (selectedTourney == 'None') {
        errorDiv.innerHTML = "Please select a tournament";
        return;
      }
  
      //Get existing subtourneys
      const subTourneyData = JSON.parse(document.getElementById("tourneyData").getAttribute('data'))
      var items = subTourneyData[selectedTourney]

      //Check if item already in array
      for (let i=0; i < items.length; i++) {
        if (newSubTourney.toLowerCase() == items[i].toLowerCase()) {
          errorDiv.innerHTML = "That sub-tournament already exists, please create a different one.";
          return;
        }
      }
  
      //Create new subtournament and reload page
      data = {'tourney': selectedTourney, 'newSubTourney': newSubTourney}
      $.ajax({
        //First, get the signed URL
        type: "POST",
        url: "/newSubTourney",
        data: data,
  
        //Next, put the data in firebase
        success: function(data) {
          if (data.result == -1) {
            alert("Failed to create the new subtournament, please contact support with the tournament + new subtournament you were trying to create")
          } else {
            errorDiv.innerHTML = "Successfully created new subtournament \"" + newSubTourney + "\" for tournament series \"" + selectedTourney + "\". It may take a minute to reflect that change here. Page will automatically be reloaded shortly.";
            errorDiv.style.color = 'rgba(172, 209, 175, 1.0)';
            
            //Reload after 5 seconds
            setTimeout(function(){
                location.reload();
              }, 5000);
          }
        }
      });
}

//File selected flag
var filesReviewed = false;

document.getElementById('theFile').onchange = function() {
    f = document.getElementById('theFile')
    errorLabel = document.getElementById("fileInfo")
    errorLabel.style.color = 'rgba(244, 113, 116, 1.0)';

    //document.getElementById("newSubTWarning").innerHTML = "";
    var uploadBtnTxt = document.getElementById("uploadBtnTxt")
    var uploadBtn = document.getElementById("uploadSubmit")
    if (document.getElementById("editUploadsBeforeUpload").checked) {
        uploadBtnTxt.innerHTML = "Review files before upload"
        uploadBtn.onclick = preUploadFiles
        uploadBtn.style.backgroundColor = "rgb(238, 238, 155);"
    }

    // Max of 500 files allowed
    numFiles = f.files.length
    if (numFiles > 500) {
        // alert('Maximum of 500 files allowed')
        errorLabel.innerHTML = "Maximum of 500 files allowed"
        document.getElementById("uploadFileForm").reset();
        return;
    }

    // Check that each file is a .slp file
    for (let i = 0; i < numFiles; i++) {
        fName = f.files.item(i).name
        fExt = fName.substring(fName.length-4, fName.length)
        if (fExt != '.slp') {
            errorLabel.innerHTML = "Only .slp files can be uploaded"
            document.getElementById("uploadFileForm").reset();
            return;
        }
    }

    // Get the total size
    totalSize = 0
    for (let i = 0; i < numFiles; i++) {
        totalSize += f.files[i].size
        totalSizeArr
    }

    // If over 2 GB of data, not allowed
    maxSize = 2 * 1024 * 1024 * 1024
    if (totalSize > maxSize) {
        errorLabel.innerHTML = "Max of 2gb of data can be uploaded at once"
        document.getElementById("uploadFileForm").reset();
        return;
    }

    errorLabel.style.color = 'rgba(172, 209, 175, 1.0)';
    errorLabel.innerHTML = numFiles + " files selected"

    filesReviewed = false;
};

//If checked, then create a video for each element in the table
function createVideosAll() {
    var checked = document.getElementById("createVideoFileCheckboxes").checked
    var table = document.getElementById("uploadTableBody")
    for (var i = 0; i < table.rows.length; i++) {
        table.rows[i].cells[1].getElementsByTagName('input')[0].checked = !checked
        table.rows[i].cells[2].getElementsByTagName('input')[0].value = ''
        table.rows[i].cells[2].getElementsByTagName('label')[0].innerHTML = ''
    }
}

//If review files checked, change the upload button
function changeUploadText() {
    var uploadBtnTxt = document.getElementById("uploadBtnTxt")
    var uploadBtn = document.getElementById("uploadSubmit")

    if (!document.getElementById("editUploadsBeforeUpload").checked) {
        uploadBtnTxt.innerHTML = "Review files before upload"
        uploadBtn.style.backgroundColor = "rgb(238, 238, 155);"
        //uploadBtn.onclick = preUploadFiles
    } else {
        uploadBtnTxt.innerHTML = "Upload"
        uploadBtn.style.backgroundColor = "rgba(0,255,0,0.3);"
        //uploadBtn.onclick = uploadFiles
    }
}

//When create video checked, remove all text in the video URL field
function onCreateVideoChecked(src) {
    if (src.checked) {
        src.parentNode.parentNode.children[2].children[0].value = ""
        src.parentNode.parentNode.children[2].getElementsByTagName('label')[0].innerHTML = ""
    }
}

//When video URL changes to something other than empty, uncheck the create video checkbox
function onVideoURLChange(e) {
    src = e.srcElement;
    var warningLabel  = $(src).parent().find('label')[0]
    warningLabel.style.color = 'rgba(244, 113, 116, 1.0)';

    if (src.value != '') {
        src.parentNode.parentNode.children[1].children[0].checked = false
        let substr = "watch?v="
        let matches = src.value.includes(substr)

        if (!matches) {
            warningLabel.innerHTML = "Please use a youtube link"
        } else if (src.value.includes("_") || src.value.includes(",") || src.value.includes("|") || src.value.includes("<") || src.value.includes(">")) {
            warningLabel.innerHTML = "Sorry, the underscore (_), comma (,), pipe (|), and chevron (<>) characters are not allowed";
        } else {
            warningLabel.innerHTML = "";
        }

    } else {
        warningLabel.innerHTML = "";
    }
}

//Validate notes to check for illegal characters
function onNotesTextChange(e) {
    src = e.srcElement;
    var warningLabel  = $(src).parent().find('label')[0]
    warningLabel.style.color = 'rgba(244, 113, 116, 1.0)';

    if (src.value != '') {
        if (src.value.includes("_") || src.value.includes(",") || src.value.includes("|") || src.value.includes("<") || src.value.includes(">")) {
            warningLabel.innerHTML = "Sorry, the underscore (_), comma (,), pipe (|), and chevron (<>) characters are not allowed";
        } else {
            warningLabel.innerHTML = "";
        }
    } else {
        warningLabel.innerHTML = "";
    }
}

//Before upload, check if any error labels have text. If so, fix that before uploading.
function checkErrorLabels() {
    var table = document.getElementById("uploadTableBody");

    for (let i = 0; i < table.rows.length; i++) {
        if (table.rows[i].cells[2].getElementsByTagName("label")[0].innerHTML != "" || table.rows[i].cells[3].getElementsByTagName("label")[0].innerHTML != "") {
            return false;
        }
    }
    return true;
}



//File uploading
var uploadsDone = 0;
var percentDone = 0;
var numFiles = 0;
var estTotalSize = 0;
var numPings = 0
var totalSizeArr = [];
var totalprogressArr = []
var progressBar = document.getElementById('fileUploadProgress')
var progressLabel = document.getElementById('progressValue')
var currentlyUploading = false

//Preupload for validating and showing table if specified
function preUploadFiles() {
    f = document.getElementById('theFile')
    errorLabel = document.getElementById("fileInfo")

    // Max of 500 files allowed
    numFiles = f.files.length
    if (numFiles > 500) {
        errorLabel.innerHTML = 'Maximum of 500 files allowed'
        document.getElementById("uploadFileForm").reset();
        errorLabel.style.color = 'rgba(244, 113, 116, 1.0)';
        return;
    }

    //Check that number of files greater than 0
    if (numFiles == 0) {
        errorLabel.innerHTML = "Please select at least 1 file to upload"
        document.getElementById("uploadFileForm").reset();
        errorLabel.style.color = 'rgba(244, 113, 116, 1.0)';
        return;
    }


    // Check that each file is a .slp file
    for (let i = 0; i < numFiles; i++) {
        fName = f.files.item(i).name
        fExt = fName.substring(fName.length-4, fName.length)
        if (fExt != '.slp') {
            errorLabel.innerHTML = 'You can only upload .slp files'
        document.getElementById("uploadFileForm").reset();
        errorLabel.style.color = 'rgba(244, 113, 116, 1.0)';
        return;
        }
    }

    // Get the total size
    totalSize = 0
    for (let i = 0; i < numFiles; i++) {
        totalSize += f.files[i].size
        totalSizeArr
    }

    // If over 2 GB of data, not allowed
    maxSize = 2 * 1024 * 1024 * 1024
    if (totalSize > maxSize) {
        errorLabel.innerHTML = 'Maximum of 2 GB allowed'
        document.getElementById("uploadFileForm").reset();
        errorLabel.style.color = 'rgba(244, 113, 116, 1.0)';
        return;
    }
    estTotalSize = totalSize

    //Check if able to upload to upload
    data = {'numFiles': numFiles}
    $.ajax({
        //Check if within user tier limits
        type: "POST",
        url: "/canDoAction",
        data: data,

        success: function(resultData) {
            //If too many actions for this tier, redirect to account page
            if (resultData.result == false) {
                window.location.href = "#account"

            //Within limit, go ahead
            } else {
                //If requested, make table
                if (document.getElementById("editUploadsBeforeUpload").checked && !filesReviewed) {
                    document.getElementById("tableContainer").style.display = "block";
                    var table = document.getElementById("uploadTableBody")
                    table.innerHTML = ""
                    if (document.getElementById("createVideoFileCheckboxes").checked) {
                        var extraText = "checked"
                    } else {
                        var extraText = ""
                    }

                    for (let i = 0; i < numFiles; i++) {
                        // Create an empty <tr> element and add it to the last position of the table:
                        var row = table.insertRow(-1);

                        // Insert new cells
                        var cell1 = row.insertCell(0);
                        var cell2 = row.insertCell(1);
                        var cell3 = row.insertCell(2);
                        var cell4 = row.insertCell(3);

                        cell1.innerHTML = f.files.item(i).name
                        cell2.innerHTML = "<input type='checkbox' id=" + i + "_createVideo " + extraText + " onClick='onCreateVideoChecked(this)'><label for=" + i + "_createVideo id=" + i + "></label>"
                        cell3.innerHTML = "<input type='text' id=" + i + "_url maxLength='128'></br><label id='" + i + "_urlError' style='rgba(244, 113, 116, 1.0)'></label>"
                        cell4.innerHTML = "<input type='text' id=" + i + "_notes maxLength='32'></br><label id=" + i + "_notesError' style='rgba(244, 113, 116, 1.0)'></label>"

                        document.getElementById(i+"_url").addEventListener('input', onVideoURLChange);
                        document.getElementById(i+'_notes').addEventListener('input', onNotesTextChange)
                    } 

                    //Change upload text
                    filesReviewed = true;
                    document.getElementById("uploadBtnTxt").innerHTML = "Upload"
                    document.getElementById("uploadBtn").backgroundColor = "rgba(0,255,0,0.3);"
                } else {
                    //Table already shown and reviewed, now we upload
                    uploadFiles()
                }
            }
        }
    });
}

//Upload files
function uploadFiles() {
    //Validate no errors showing
    if (!checkErrorLabels()) {
        errorLabel.innerHTML = "Please resolve all errors listed in the table below before uploading"
        errorLabel.style.color = 'rgba(244, 113, 116, 1.0)';
        return;
    }

    //Remove error text and get # of files
    errorLabel.innerHTML = ""
    f = document.getElementById('theFile')
    numFiles = f.files.length

    // Reset progressBar items
    uploadsDone = 0;
    totalProgress = 0;
    numPings = 0
    percentDone = '0%'
    totalSizeArr = new Array(numFiles)
    totalProgressArr = new Array(numFiles)
    value = '0%'; 
    progressBar.value = 0
    progressLabel.innerHTML = "0/" + numFiles + ", " + value
    currentlyUploading = true

    //Get tourney/subtourney
    var tourney = document.getElementById("tourneyInput").value
    var subTourney = document.getElementById("subTourneyInput").value

    //Disable choosefile and upload buttons
    var uploadBtn = document.getElementById("uploadSubmit");
    uploadBtn.removeAttribute('onclick')
    uploadBtn.style.color = 'gray';
    f.style.color = 'gray'
    f.disabled = true;
    filesReviewed = false;

    //Hide table and disable the checkboxes
    document.getElementById("tableContainer").style.display = "none";
    document.getElementById("createVideoFileCheckboxes").disabled = true;
    document.getElementById("editUploadsBeforeUpload").disabled = true;

    //Get table element
    var table = document.getElementById("uploadTableBody")

    //Update firebase counts
    data = {'numFiles': numFiles}
    $.ajax({
        //First, get the signed URL
        type: "POST",
        url: "/updateFirebase",
        data: data,
    });

    //For each file, get name and ext, get signed upload URL, and upload
    for (let i = 0; i < numFiles; i++) {
        //Get name and ext
        fName = f.files.item(i).name
        fExt = fName.substring(fName.length-4, fName.length)

        //Try and get the video or video url + note related to the file
        video = 0
        notes = ''
        if (editUploadsBeforeUpload.checked) {
            try {
                notes = table.rows[i].cells[3].getElementsByTagName('input')[0].value
                
                //If a video of some kind was specified, do that
                if (table.rows[i].cells[1].getElementsByTagName('input')[0].checked) {
                    video = 1
                } else if (table.rows[i].cells[2].getElementsByTagName('input')[0].value != '') {
                    video = table.rows[i].cells[2].getElementsByTagName('input')[0].value
                    video = video.substring(video.indexOf("watch?v=") + "watch?v=".length, video.indexOf("watch?v=") + "watch?v=".length + 11)
                    
                }
            } catch (error) {
                video = 0
                notes = ''
            }
        } else if (!editUploadsBeforeUpload.checked && createVideoFileCheckboxes.checked) {
            video = 1
        }

        //Get signed URL for upload
        var urlData = {'tourney': tourney, 'subTourney': subTourney, 'video': video, 'notes': notes, 'ext': fExt}
        var contentType
        if (fExt === '.zip') { contentType = "application/zip"; } 
        else if (fExt === '.slp') { contentType = "application/octet-stream"; } 

        $.ajax({
            //First, get the signed URL
            type: "POST",
            url: "/signedUploadURL",
            data: urlData,

            //Next, put the data in GCS
            success: function(data) {
                if (data.presigned_url == -1) {
                    alert("Failed to generate the upload URL, please contact support")
                } else {
                    uploadFile(data.presigned_url, i, numFiles)
                }
            }
        });
    }

}

//Upload individual file using xhr and form data
function uploadFile(url, idx) {
    var upload_files = document.getElementById('theFile');

    //Create form data and xhr request
    let formData = new FormData();
    formData.append("file", upload_files.files[idx]);

    //Put the URL and get the content type header
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url);
    fName = upload_files.files.item(idx).name
    fExt = fName.substring(fName.length-4, fName.length)

    //Add event listeners for the file
    xhr.addEventListener('loadstart', handleEvent);
    xhr.addEventListener('load', handleEvent);
    xhr.addEventListener('loadend', handleEvent);
    xhr.addEventListener('error', handleEvent);
    xhr.addEventListener('abort', handleEvent);
    xhr.upload.addEventListener('progress', handleEvent);

    //Send the data
    xhr.send(formData);

}

//Handle event - mostly used for progress/loadend events
function handleEvent(e) {

    //Done uploading
    if (e.type == "loadend") {
        uploadsDone += 1
        progressLabel.innerHTML = uploadsDone + "/" + numFiles + " files uploaded, " + percentDone

        //If uploads done == numFiles then done uploading
        if (uploadsDone == numFiles) {
            //Get elements
            var uploadBtn = document.getElementById("uploadSubmit");
            var f = document.getElementById('theFile');
            
            //Set progress label and re-enable onclick event for uploadBtn
            progressLabel.innerHTML = uploadsDone + "/" + numFiles + " files uploaded, " + percentDone + ', done uploading'
            uploadBtn.onclick = preUploadFiles
            uploadBtn.style.color = 'white';

            //Reset file color style and reset uploading flag
            f.style.color = 'white'
            f.disabled = false;
            currentlyUploading = false
            
            //If review before upload, reset the button style/text
            if (document.getElementById("editUploadsBeforeUpload").checked) {
                document.getElementById("uploadBtnTxt").innerHTML = "Review files before upload"
                document.getElementById("uploadBtn").style.backgroundColor = "rgb(238, 238, 155);"
            }

            //Delete table and re-enable buttons
            document.getElementById("uploadTableBody").innerHTML = ""
            document.getElementById("createVideoFileCheckboxes").disabled = false;
            document.getElementById("editUploadsBeforeUpload").disabled = false;
        }

    } else if (e.type == "progress") {

        //Check if the total is in the array
        const isTotal = (element) => element == e.total;
        const isEmpty = (element) => element == null;
        var total = parseInt(e.total)
        
        //If the idx isn't found, then just get the first open idx
        var idx = totalSizeArr.findIndex(isTotal)
        if (idx == -1) {
            //Get first 0 index
            var firstOpening = totalSizeArr.findIndex(isEmpty)
            idx = firstOpening
        }

        //Assign values
        totalSizeArr[idx] = e.total
        totalProgressArr[idx] = e.loaded

        //Get the total progress
        var totalProgress = totalProgressArr.reduce(function(pv, cv) { return pv + cv; }, 0);
        var totalSize = totalSizeArr.reduce(function(pv, cv) { return pv + cv; }, 0);

        if (numPings < numFiles * 3) {
            totalSize = estTotalSize
        }

        // console.log(totalProgress)
        percentDone = Math.round((totalProgress / totalSize) * 100) + '%';
        progressLabel.innerHTML = uploadsDone + "/" + numFiles + " files uploaded, " + percentDone
        progressBar.value = Math.round((totalProgress / totalSize) * 100)
    }
}

//Just gives the user an "Are you sure?" message before navigating away from page
window.onbeforeunload = function() {
    if (currentlyUploading) {
        return 'No'
    }
}