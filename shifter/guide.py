# Built-in
import datetime
import getpass
import imp
import json
import os
import shutil
import subprocess
import sys
import traceback
from functools import partial

# pymel
import pymel.core as pm
from pymel.core import datatypes

# mgear
import mgear
from mgear.core import attribute, dag, vector, pyqt, skin, string, fcurve
from mgear.core import utils, curve
from mgear.vendor.Qt import QtCore, QtWidgets, QtGui

from . import guideUI as guui
from . import customStepUI as csui

# pyside
from maya.app.general.mayaMixin import MayaQDockWidget
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

GUIDE_UI_WINDOW_NAME = "guide_UI_window"
GUIDE_DOCK_NAME = "Guide_Components"

TYPE = "mgear_guide_root"

MGEAR_SHIFTER_CUSTOMSTEP_KEY = "MGEAR_SHIFTER_CUSTOMSTEP_PATH"


class Main(object):
    """The main guide class

    Provide the methods to add parameters, set parameter values,
    create property...

    Attributes:
        paramNames (list): List of parameter name cause it's actually important
        to keep them sorted.
        paramDefs (dict): Dictionary of parameter definition.
        values (dict): Dictionary of options values.
        valid (bool): We will check a few things and make sure the guide we are
            loading is up to date. If parameters or object are missing a
            warning message will be display and the guide should be updated.

    """

    def __init__(self):

        self.paramNames = []
        self.paramDefs = {}
        self.values = {}
        self.valid = True

    def addPropertyParamenters(self, parent):
        """Add attributes from the parameter definition list

        Arguments:
            parent (dagNode): The object to add the attributes.

        Returns:
            dagNode: parent with the attributes.

        """

        for scriptName in self.paramNames:
            paramDef = self.paramDefs[scriptName]
            paramDef.create(parent)

        return parent

    def setParamDefValue(self, scriptName, value):
        """Set the value of parameter with matching scriptname.

        Arguments:
            scriptName (str): Scriptname of the parameter to edit.
            value (variant): New value.

        Returns:
            bool: False if the parameter wasn't found.

        """

        if scriptName not in self.paramDefs.keys():
            mgear.log("Can't find parameter definition for : " + scriptName,
                      mgear.sev_warning)
            return False

        self.paramDefs[scriptName].value = value
        self.values[scriptName] = value

        return True

    def setParamDefValuesFromDict(self, values_dict):
        for scriptName, paramDef in self.paramDefs.items():
            paramDef.value = values_dict[scriptName]
            self.values[scriptName] = values_dict[scriptName]

    def setParamDefValuesFromProperty(self, node):
        """Set the parameter definition values from the attributes of an object

        Arguments:
            node (dagNode): The object with the attributes.
        """

        for scriptName, paramDef in self.paramDefs.items():
            if not pm.attributeQuery(scriptName, node=node, exists=True):
                mgear.log("Can't find parameter '%s' in %s" %
                          (scriptName, node), mgear.sev_warning)
                self.valid = False
            else:
                cnx = pm.listConnections(
                    node + "." + scriptName,
                    destination=False, source=True)
                if isinstance(paramDef, attribute.FCurveParamDef):
                    paramDef.value = fcurve.getFCurveValues(
                        cnx[0],
                        self.get_divisions())
                    self.values[scriptName] = paramDef.value
                elif cnx:
                    paramDef.value = None
                    self.values[scriptName] = cnx[0]
                else:
                    paramDef.value = pm.getAttr(node + "." + scriptName)
                    self.values[scriptName] = pm.getAttr(
                        node + "." + scriptName)

    def addColorParam(self, scriptName, value=False):
        """Add color paramenter to the paramenter definition Dictionary.

        Arguments:
            scriptName (str): The name of the color parameter.
            value (Variant): The default color value.

        Returns:
            paramDef: The newly create paramenter definition.
        """

        paramDef = attribute.colorParamDef(scriptName, value)
        self.paramDefs[scriptName] = paramDef
        self.paramNames.append(scriptName)

        return paramDef

    def addParam(self, scriptName, valueType, value,
                 minimum=None, maximum=None, keyable=False,
                 readable=True, storable=True, writable=True,
                 niceName=None, shortName=None):
        """Add paramenter to the paramenter definition Dictionary.

        Arguments:
            scriptName (str): Parameter scriptname.
            valueType (str): The Attribute Type. Exp: 'string', 'bool',
                'long', etc..
            value (float or int): Default parameter value.
            niceName (str): Parameter niceName.
            shortName (str): Parameter shortName.
            minimum (float or int): mininum value.
            maximum (float or int): maximum value.
            keyable (boo): If true is keyable
            readable (boo): If true is readable
            storable (boo): If true is storable
            writable (boo): If true is writable

        Returns:
            paramDef: The newly create paramenter definition.

        """
        paramDef = attribute.ParamDef2(scriptName, valueType, value, niceName,
                                       shortName, minimum, maximum, keyable,
                                       readable, storable, writable)
        self.paramDefs[scriptName] = paramDef
        self.values[scriptName] = value
        self.paramNames.append(scriptName)

        return paramDef

    def addFCurveParam(self, scriptName, keys, interpolation=0):
        """Add FCurve paramenter to the paramenter definition Dictionary.

        Arguments:
            scriptName (str): Attribute fullName.
            keys (list): The keyframes to define the function curve.
            interpolation (int): the curve interpolation.

        Returns:
            paramDef: The newly create paramenter definition.

        """
        paramDef = attribute.FCurveParamDef(scriptName, keys, interpolation)
        self.paramDefs[scriptName] = paramDef
        self.values[scriptName] = None
        self.paramNames.append(scriptName)

        return paramDef

    def addEnumParam(self, scriptName, enum, value=False):
        """Add FCurve paramenter to the paramenter definition Dictionary.

        Arguments:
            scriptName (str): Attribute fullName
            enum (list of str): The list of elements in the enumerate control.
            value (int): The default value.

        Returns:
            paramDef: The newly create paramenter definition.

        """
        paramDef = attribute.enumParamDef(scriptName, enum, value)
        self.paramDefs[scriptName] = paramDef
        self.values[scriptName] = value
        self.paramNames.append(scriptName)

        return paramDef

    def get_param_values(self):
        param_values = {}
        for pn in self.paramNames:
            pd = self.paramDefs[pn].get_as_dict()
            param_values[pn] = pd['value']

        return param_values

##########################################################
# RIG GUIDE
##########################################################


class Rig(Main):
    """Rig guide class.

    This is the class for complete rig guide definition.

        * It contains the component guide in correct hierarchy order and the
            options to generate the rig.
        * Provide the methods to add more component, import/export guide.

    Attributes:
        paramNames (list): List of parameter name cause it's actually important
            to keep them sorted.
        paramDefs (dict): Dictionary of parameter definition.
        values (dict): Dictionary of options values.
        valid (bool): We will check a few things and make sure the guide we are
            loading is up to date. If parameters or object are missing a
            warning message will be display and the guide should be updated.
        controllers (dict): Dictionary of controllers.
        components (dict): Dictionary of component. Keys are the component
            fullname (ie. 'arm_L0')
        componentsIndex (list): List of component name sorted by order
            creation (hierarchy order)
        parents (list): List of the parent of each component, in same order
            as self.components
    """

    def __init__(self):

        # Parameters names, definition and values.
        self.paramNames = []
        self.paramDefs = {}
        self.values = {}
        self.valid = True

        self.controllers = {}
        self.components = {}  # Keys are the component fullname (ie. 'arm_L0')
        self.componentsIndex = []
        self.parents = []

        self.guide_template_dict = {}  # guide template dict to export guides

        self.addParameters()

    def addParameters(self):
        """Parameters for rig options.

        Add more parameter to the parameter definition list.

        """
        # --------------------------------------------------
        # Main Tab
        self.pRigName = self.addParam("rig_name", "string", "rig")
        self.pMode = self.addEnumParam("mode", ["Final", "WIP"], 0)
        self.pStep = self.addEnumParam(
            "step",
            ["All Steps", "Objects", "Properties",
                "Operators", "Connect", "Joints", "Finalize"],
            6)
        self.pIsModel = self.addParam("ismodel", "bool", True)
        self.pClassicChannelNames = self.addParam(
            "classicChannelNames",
            "bool",
            True)
        self.pProxyChannels = self.addParam("proxyChannels", "bool", False)
        self.pWorldCtl = self.addParam("worldCtl", "bool", False)

        # --------------------------------------------------
        # skin
        self.pSkin = self.addParam("importSkin", "bool", False)
        self.pSkinPackPath = self.addParam("skin", "string", "")

        # --------------------------------------------------
        # Colors

        # Index color
        self.pLColorIndexfk = self.addParam("L_color_fk", "long", 6, 0, 31)
        self.pLColorIndexik = self.addParam("L_color_ik", "long", 18, 0, 31)
        self.pRColorIndexfk = self.addParam("R_color_fk", "long", 23, 0, 31)
        self.pRColorIndexik = self.addParam("R_color_ik", "long", 14, 0, 31)
        self.pCColorIndexfk = self.addParam("C_color_fk", "long", 13, 0, 31)
        self.pCColorIndexik = self.addParam("C_color_ik", "long", 17, 0, 31)

        # RGB colors for Maya 2015 and up
        # self.pLColorfk = self.addColorParam("L_RGB_fk", [0, 1, 0])
        # self.pLColorik = self.addColorParam("L_RGB_ik", [0, .5, 0])
        # self.pRColorfk = self.addColorParam("R_RGB_fk", [0, 0, 1])
        # self.pRColorik = self.addColorParam("R_RGB_ik", [0, 0, .6])
        # self.pCColorfk = self.addColorParam("C_RGB_fk", [1, 0, 0])
        # self.pCColorik = self.addColorParam("C_RGB_ik", [.6, 0, 0])

        # --------------------------------------------------
        # Settings
        self.pJointRig = self.addParam("joint_rig", "bool", True)
        self.pJointRig = self.addParam("force_uniScale", "bool", False)
        self.pSynoptic = self.addParam("synoptic", "string", "")

        self.pDoPreCustomStep = self.addParam("doPreCustomStep", "bool", False)
        self.pDoPostCustomStep = self.addParam("doPostCustomStep",
                                               "bool", False)
        self.pPreCustomStep = self.addParam("preCustomStep", "string", "")
        self.pPostCustomStep = self.addParam("postCustomStep", "string", "")

        # --------------------------------------------------
        # Comments
        self.pComments = self.addParam("comments", "string", "")
        self.pUser = self.addParam("user", "string", getpass.getuser())
        self.pDate = self.addParam(
            "date", "string", str(datetime.datetime.now()))
        self.pMayaVersion = self.addParam(
            "maya_version", "string",
            str(pm.mel.eval("getApplicationVersionAsFloat")))
        self.pGearVersion = self.addParam(
            "gear_version", "string", mgear.getVersion())

    def setFromSelection(self):
        """Set the guide hierarchy from selection."""
        selection = pm.ls(selection=True)
        if not selection:
            mgear.log(
                "Select one or more guide root or a guide model",
                mgear.sev_error)
            self.valid = False
            return False

        for node in selection:
            self.setFromHierarchy(node, node.hasAttr("ismodel"))

        return True

    def setFromHierarchy(self, root, branch=True):
        """Set the guide from given hierarchy.

        Arguments:
            root (dagNode): The root of the hierarchy to parse.
            branch (bool): True to parse children components.

        """
        startTime = datetime.datetime.now()
        # Start
        mgear.log("Checking guide")

        # Get the model and the root
        self.model = root.getParent(generations=-1)
        while True:
            if root.hasAttr("comp_type") or self.model == root:
                break
            root = root.getParent()
            mgear.log(root)

        # ---------------------------------------------------
        # First check and set the options
        mgear.log("Get options")
        self.setParamDefValuesFromProperty(self.model)

        # ---------------------------------------------------
        # Get the controllers
        mgear.log("Get controllers")
        self.controllers_org = dag.findChild(self.model, "controllers_org")
        if self.controllers_org:
            for child in self.controllers_org.getChildren():
                self.controllers[child.name().split("|")[-1]] = child

        # ---------------------------------------------------
        # Components
        mgear.log("Get components")
        self.findComponentRecursive(root, branch)
        endTime = datetime.datetime.now()
        finalTime = endTime - startTime
        mgear.log("Find recursive in  [ " + str(finalTime) + " ]")
        # Parenting
        if self.valid:
            for name in self.componentsIndex:
                mgear.log("Get parenting for: " + name)
                # TODO: In the future should use connections to retrive this
                # data
                # We try the fastes aproach, will fail if is not the top node
                try:
                    # search for his parent
                    compParent = self.components[name].root.getParent()
                    if compParent and compParent.hasAttr("isGearGuide"):
                        pName = "_".join(compParent.name().split("_")[:2])
                        pLocal = "_".join(compParent.name().split("_")[2:])

                        pComp = self.components[pName]
                        self.components[name].parentComponent = pComp
                        self.components[name].parentLocalName = pLocal
                # This will scan the hierachy in reverse. It is much slower
                except KeyError:
                    # search children and set him as parent
                    compParent = self.components[name]
                    # for localName, element in compParent.getObjects(
                    #         self.model, False).items():
                    # NOTE: getObjects3 is an experimental function
                    for localName, element in compParent.getObjects3(
                            self.model).items():
                        for name in self.componentsIndex:
                            compChild = self.components[name]
                            compChild_parent = compChild.root.getParent()
                            if (element is not None
                                    and element == compChild_parent):
                                compChild.parentComponent = compParent
                                compChild.parentLocalName = localName

            # More option values
            self.addOptionsValues()

        # End
        if not self.valid:
            mgear.log("The guide doesn't seem to be up to date."
                      "Check logged messages and update the guide.",
                      mgear.sev_warning)

        endTime = datetime.datetime.now()
        finalTime = endTime - startTime
        mgear.log("Guide loaded from hierarchy in  [ " + str(finalTime) + " ]")

    def set_from_dict(self, guide_template_dict):

        r_dict = guide_template_dict['guide_root']

        self.setParamDefValuesFromDict(r_dict["param_values"])

        components_dict = guide_template_dict["components_dict"]
        self.componentsIndex = guide_template_dict["components_list"]

        for comp in self.componentsIndex:

            c_dict = components_dict[comp]

            # WIP  Now need to set each component from dict.
            comp_type = c_dict["param_values"]["comp_type"]
            comp_guide = self.getComponentGuide(comp_type)
            if comp_guide:
                self.components[comp] = comp_guide
                comp_guide.set_from_dict(c_dict)

            pName = c_dict["parent_fullName"]
            if pName:
                pComp = self.components[pName]
                self.components[comp].parentComponent = pComp
                p_local_name = c_dict["parent_localName"]
                self.components[comp].parentLocalName = p_local_name

    def get_guide_template_dict(self):

        # Guide Root
        root_dict = {}
        root_dict["tra"] = self.model.getMatrix(worldSpace=True).get()
        root_dict["name"] = self.model.shortName()
        root_dict["param_values"] = self.get_param_values()
        self.guide_template_dict["guide_root"] = root_dict

        # Components
        components_list = []
        components_dict = {}
        for comp in self.componentsIndex:
            comp_guide = self.components[comp]
            c_name = comp_guide.fullName
            components_list.append(c_name)
            c_dict = comp_guide.get_guide_template_dict()
            components_dict[c_name] = c_dict
            if c_dict["parent_fullName"]:
                pn = c_dict["parent_fullName"]
                components_dict[pn]["child_components"].append(c_name)

        self.guide_template_dict["components_list"] = components_list
        self.guide_template_dict["components_dict"] = components_dict

        # controls shape buffers
        co = pm.ls("controllers_org")
        if co and co[0] in pm.selected()[0].listRelatives(children=True):
            ctl_buffers = co[0].listRelatives(children=True)
            ctl_buffers_dict = curve.collect_curve_data(objs=ctl_buffers)
            self.guide_template_dict["ctl_buffers_dict"] = ctl_buffers_dict

        else:
            pm.displayWarning("Can't find controllers_org in order to retrive"
                              " the controls shapes buffer")
            self.guide_template_dict["ctl_buffers_dict"] = None

        return self.guide_template_dict

    def addOptionsValues(self):
        """Gather or change some options values according to some others.

        Note:
            For the moment only gets the rig size to adapt size of object to
            the scale of the character

        """
        # Get rig size to adapt size of object to the scale of the character
        maximum = 1
        v = datatypes.Vector()
        for comp in self.components.values():
            for pos in comp.apos:
                d = vector.getDistance(v, pos)
                maximum = max(d, maximum)

        self.values["size"] = max(maximum * .05, .1)

    def findComponentRecursive(self, node, branch=True):
        """Finds components by recursive search.

        Arguments:
            node (dagNode): Object frome where start the search.
            branch (bool): If True search recursive all the children.
        """

        if node.hasAttr("comp_type"):
            comp_type = node.getAttr("comp_type")
            comp_guide = self.getComponentGuide(comp_type)

            if comp_guide:
                comp_guide.setFromHierarchy(node)
                mgear.log(comp_guide.fullName + " (" + comp_type + ")")
                if not comp_guide.valid:
                    self.valid = False

                self.componentsIndex.append(comp_guide.fullName)
                self.components[comp_guide.fullName] = comp_guide

        if branch:
            for child in node.getChildren(type="transform"):
                self.findComponentRecursive(child)

    def getComponentGuide(self, comp_type):
        """Get the componet guide python object

        ie. Finds the guide.py of the component.

        Arguments:
            comp_type (str): The component type.

        Returns:
            The component guide instance class.
        """

        # Check component type
        '''
        path = os.path.join(basepath, comp_type, "guide.py")
        if not os.path.exists(path):
            mgear.log("Can't find guide definition for : " + comp_type + ".\n"+
                path, mgear.sev_error)
            return False
        '''

        # Import module and get class
        import mgear.shifter as shifter
        module = shifter.importComponentGuide(comp_type)

        ComponentGuide = getattr(module, "Guide")

        return ComponentGuide()

    # =====================================================
    # DRAW

    def initialHierarchy(self):
        """Create the initial rig guide hierarchy (model, options...)"""
        self.model = pm.group(n="guide", em=True, w=True)

        # Options
        self.options = self.addPropertyParamenters(self.model)

        # the basic org nulls (Maya groups)
        self.controllers_org = pm.group(
            n="controllers_org",
            em=True,
            p=self.model)
        self.controllers_org.attr('visibility').set(0)

    def drawNewComponent(self, parent, comp_type, showUI=True):
        """Add a new component to the guide.

        Arguments:
            parent (dagNode): Parent of this new component guide.
            compType (str): Type of component to add.

        """
        comp_guide = self.getComponentGuide(comp_type)

        if not comp_guide:
            mgear.log("Not component guide of type: " + comp_type +
                      " have been found.", mgear.sev_error)
            return
        if parent is None:
            self.initialHierarchy()
            parent = self.model
        else:
            parent_root = parent
            while True:
                if parent_root.hasAttr("ismodel"):
                    break

                if parent_root.hasAttr("comp_type"):
                    parent_type = parent_root.attr("comp_type").get()
                    parent_side = parent_root.attr("comp_side").get()
                    parent_uihost = parent_root.attr("ui_host").get()
                    parent_ctlGrp = parent_root.attr("ctlGrp").get()

                    if parent_type in comp_guide.connectors:
                        comp_guide.setParamDefValue("connector", parent_type)

                    comp_guide.setParamDefValue("comp_side", parent_side)
                    comp_guide.setParamDefValue("ui_host", parent_uihost)
                    comp_guide.setParamDefValue("ctlGrp", parent_ctlGrp)

                    break

                parent_root = parent_root.getParent()

        comp_guide.drawFromUI(parent, showUI)

    def drawUpdate(self, oldRoot, parent=None):

        # Initial hierarchy
        if parent is None:
            self.initialHierarchy()
            parent = self.model
            newParentName = parent.name()

        # controls shape
        try:
            pm.delete(pm.PyNode(newParentName + "|controllers_org"))
            oldRootName = oldRoot.name().split("|")[0] + "|controllers_org"
            pm.parent(oldRootName, newParentName)
        except TypeError:
            pm.displayError("The guide don't have controllers_org")

        # Components
        for name in self.componentsIndex:
            comp_guide = self.components[name]
            oldParentName = comp_guide.root.getParent().name()

            try:
                parent = pm.PyNode(oldParentName.replace(
                    oldParentName.split("|")[0], newParentName))
            except TypeError:
                pm.displayWarning("No parent for the guide")
                parent = self.model

            comp_guide.draw(parent)

    @utils.timeFunc
    def draw_guide(self, partial=None, initParent=None):
        """Draw a new guide from  the guide object.
        Usually the information of the guide have been set from a configuration
        Dictionary

        Args:
            partial (str or list of str, optional): If Partial starting
                component is defined, will try to add the guide to a selected
                guide part of an existing guide.
            initParent (dagNode, optional): Initial parent. If None, will
                create a new initial heirarchy

        Example:
            shifter.log_window()
            rig = shifter.Rig()
            rig.guide.set_from_dict(conf_dict)
            # draw complete guide
            rig.guide.draw_guide()
            # add to existing guide
            # rig.guide.draw_guide(None, pm.selected()[0])
            # draw partial guide
            # rig.guide.draw_guide(["arm_R0", "leg_L0"])
            # draw partial guide adding to existing guide
            # rig.guide.draw_guide(["arm_R0", "leg_L0"], pm.selected()[0])

        Returns:
            TYPE: Description
        """
        partial_components = None
        partial_components_idx = []
        parent = None

        if partial:
            if not isinstance(partial, list):
                partial = [partial]  # track the original partial components
            # clone list track all child partial
            partial_components = list(partial)

        if initParent:
            if initParent and initParent.getParent(-1).hasAttr("ismodel"):
                self.model = initParent.getParent(-1)
            else:
                pm.displayWarning("Current initial parent is not part of "
                                  "a valid Shifter guide element")
                return
        else:
            self.initialHierarchy()

        # Components
        for name in self.componentsIndex:
            comp_guide = self.components[name]

            if comp_guide.parentComponent:
                try:
                    parent = pm.PyNode(comp_guide.parentComponent.getName(
                        comp_guide.parentLocalName))
                except pm.MayaNodeError:
                    # if we have a name clashing in the scene, it will try for
                    # find the parent by crawling the hierarchy. This will take
                    # longer time.
                    parent = dag.findChild(
                        self.model,
                        comp_guide.parentComponent.getName(
                            comp_guide.parentLocalName))

            if not parent and initParent:
                parent = initParent
            elif not parent:
                parent = self.model

            # Partial build logic
            if partial and name in partial_components:
                for chd in comp_guide.child_components:
                    partial_components.append(chd)

                # need to reset the parent for partial build since will loop
                # the guide from the root and will set again the parent to None
                if name in partial and initParent:
                    # Check if component is in initial partial to reset the
                    # parent
                    parent = initParent
                elif name in partial and not initParent:
                    parent = self.model
                elif not parent and initParent:
                    parent = initParent

                comp_guide.draw(parent)

                partial_components_idx.append(comp_guide.values["comp_index"])

            if not partial:  # if not partial will build all the components
                comp_guide.draw(parent)

        return partial_components, partial_components_idx

    def update(self, sel, force=False):
        """Update the guide if a parameter is missing"""

        if pm.attributeQuery("ismodel", node=sel, ex=True):
            self.model = sel
        else:
            pm.displayWarning("select the top guide node")
            return

        name = self.model.name()
        self.setFromHierarchy(self.model, True)
        if self.valid and not force:
            pm.displayInfo("The Guide is updated")
            return

        pm.rename(self.model, name + "_old")
        deleteLater = self.model
        self.drawUpdate(deleteLater)
        pm.rename(self.model, name)
        pm.displayInfo("The guide %s have been updated" % name)
        pm.delete(deleteLater)

    def duplicate(self, root, symmetrize=False):
        """Duplicate the guide hierarchy

        Note:
            Indeed this method is not duplicating.
            What it is doing is parse the compoment guide,
            and creating an new one base on the current selection.

        Warning:
            Don't use the default Maya's duplicate tool to duplicate a
            Shifter's guide.


        Arguments:
            root (dagNode): The guide root to duplicate.
            symmetrize (bool): If True, duplicate symmetrical in X axis.
            The guide have to be "Left" or "Right".

        """
        if not pm.attributeQuery("comp_type", node=root, ex=True):
            mgear.log("Select a component root to duplicate", mgear.sev_error)
            return

        self.setFromHierarchy(root)
        for name in self.componentsIndex:
            comp_guide = self.components[name]
            if symmetrize:
                if not comp_guide.symmetrize():
                    return

        # Draw
        if pm.attributeQuery("ismodel", node=root, ex=True):
            self.draw()

        else:

            for name in self.componentsIndex:
                comp_guide = self.components[name]

                if comp_guide.parentComponent is None:
                    parent = comp_guide.root.getParent()
                    if symmetrize:
                        parent = dag.findChild(
                            self.model,
                            string.convertRLName(
                                comp_guide.root.getParent().name()))
                        if not parent:
                            parent = comp_guide.root.getParent()

                    else:
                        parent = comp_guide.root.getParent()

                else:
                    parent = dag.findChild(
                        self.model,
                        comp_guide.parentComponent.getName(
                            comp_guide.parentLocalName))
                    if not parent:
                        mgear.log(
                            "Unable to find parent (%s.%s) for guide %s" %
                            (comp_guide.parentComponent.getFullName,
                                comp_guide.parentLocalName,
                                comp_guide.getFullName))
                        parent = self.model

                # Reset the root so we force the draw to duplicate
                comp_guide.root = None

                comp_guide.setIndex(self.model)

                comp_guide.draw(parent)

        pm.select(self.components[self.componentsIndex[0]].root)

    def updateProperties(self, root, newName, newSide, newIndex):
        """Update the Properties of the component.

        Arguments:
            root (dagNode): Root of the component.
            newName (str): New name of the component
            newSide (str): New side of the component
            newIndex (str): New index of the component
        """

        if not pm.attributeQuery("comp_type", node=root, ex=True):
            mgear.log("Select a root to edit properties", mgear.sev_error)
            return
        self.setFromHierarchy(root, False)
        name = "_".join(root.name().split("|")[-1].split("_")[0:2])
        comp_guide = self.components[name]
        comp_guide.rename(root, newName, newSide, newIndex)


class HelperSlots(object):

    def updateHostUI(self, lEdit, targetAttr):
        oType = pm.nodetypes.Transform

        oSel = pm.selected()
        if oSel:
            if isinstance(oSel[0], oType) and oSel[0].hasAttr("isGearGuide"):
                lEdit.setText(oSel[0].name())
                self.root.attr(targetAttr).set(lEdit.text())
            else:
                pm.displayWarning("The selected element is not a "
                                  "valid object or not from a guide")
        else:
            pm.displayWarning("Please select first the object.")

    def updateLineEdit(self, lEdit, targetAttr):
        name = string.removeInvalidCharacter(lEdit.text())
        self.root.attr(targetAttr).set(name)

    def addItem2listWidget(self, listWidget, targetAttr=None):

        items = pm.selected()
        itemsList = [i.text() for i in listWidget.findItems(
            "", QtCore.Qt.MatchContains)]
        # Quick clean the first empty item
        if itemsList and not itemsList[0]:
            listWidget.takeItem(0)

        for item in items:
            if item.name() not in itemsList:
                if item.hasAttr("isGearGuide"):
                    listWidget.addItem(item.name())

                else:
                    pm.displayWarning(
                        "The object: %s, is not a valid"
                        " reference, Please select only guide componet"
                        " roots and guide locators." % item.name())
            else:
                pm.displayWarning("The object: %s, is already in the list." %
                                  item.name())

        if targetAttr:
            self.updateListAttr(listWidget, targetAttr)

    def removeSelectedFromListWidget(self, listWidget, targetAttr=None):
        for item in listWidget.selectedItems():
            listWidget.takeItem(listWidget.row(item))
        if targetAttr:
            self.updateListAttr(listWidget, targetAttr)

    def moveFromListWidget2ListWidget(self, sourceListWidget, targetListWidget,
                                      targetAttrListWidget, targetAttr=None):
        # Quick clean the first empty item
        itemsList = [i.text() for i in targetAttrListWidget.findItems(
            "", QtCore.Qt.MatchContains)]
        if itemsList and not itemsList[0]:
            targetAttrListWidget.takeItem(0)

        for item in sourceListWidget.selectedItems():
            targetListWidget.addItem(item.text())
            sourceListWidget.takeItem(sourceListWidget.row(item))

        if targetAttr:
            self.updateListAttr(targetAttrListWidget, targetAttr)

    def copyFromListWidget(self, sourceListWidget, targetListWidget,
                           targetAttr=None):
        targetListWidget.clear()
        itemsList = [i.text() for i in sourceListWidget.findItems(
            "", QtCore.Qt.MatchContains)]
        for item in itemsList:
            targetListWidget.addItem(item)
        if targetAttr:
            self.updateListAttr(sourceListWidget, targetAttr)

    def updateListAttr(self, sourceListWidget, targetAttr):
        """Update the string attribute with values separated by commas"""
        newValue = ",".join([i.text() for i in sourceListWidget.findItems(
            "", QtCore.Qt.MatchContains)])
        self.root.attr(targetAttr).set(newValue)

    def updateComponentName(self):

        newName = self.mainSettingsTab.name_lineEdit.text()
        # remove invalid characters in the name and update
        newName = string.removeInvalidCharacter(newName)
        self.mainSettingsTab.name_lineEdit.setText(newName)
        sideSet = ["C", "L", "R"]
        sideIndex = self.mainSettingsTab.side_comboBox.currentIndex()
        newSide = sideSet[sideIndex]
        newIndex = self.mainSettingsTab.componentIndex_spinBox.value()
        guide = Rig()
        guide.updateProperties(self.root, newName, newSide, newIndex)
        pm.select(self.root, r=True)
        # sync index
        self.mainSettingsTab.componentIndex_spinBox.setValue(
            self.root.attr("comp_index").get())

    def updateConnector(self, sourceWidget, itemsList, *args):
        self.root.attr("connector").set(itemsList[sourceWidget.currentIndex()])

    def populateCheck(self, targetWidget, sourceAttr, *args):
        if self.root.attr(sourceAttr).get():
            targetWidget.setCheckState(QtCore.Qt.Checked)
        else:
            targetWidget.setCheckState(QtCore.Qt.Unchecked)

    def updateCheck(self, sourceWidget, targetAttr, *args):
        self.root.attr(targetAttr).set(sourceWidget.isChecked())

    def updateSpinBox(self, sourceWidget, targetAttr, *args):
        self.root.attr(targetAttr).set(sourceWidget.value())
        return True

    def updateSlider(self, sourceWidget, targetAttr, *args):
        self.root.attr(targetAttr).set(float(sourceWidget.value()) / 100)

    def updateComboBox(self, sourceWidget, targetAttr, *args):
        self.root.attr(targetAttr).set(sourceWidget.currentIndex())

    def updateControlShape(self, sourceWidget, ctlList, targetAttr, *args):
        curIndx = sourceWidget.currentIndex()
        self.root.attr(targetAttr).set(ctlList[curIndx])

    def setProfile(self):
        pm.select(self.root, r=True)
        pm.runtime.GraphEditor()

    def close_settings(self):
        self.close()
        pyqt.deleteInstances(self, MayaQDockWidget)

    def editFile(self, widgetList):
        try:
            filepath = widgetList.selectedItems()[0].text().split("|")[-1][1:]
            if os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""):
                editPath = os.path.join(
                    os.environ.get(
                        MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""), filepath)
            else:
                editPath = filepath
            if filepath:
                if sys.platform.startswith('darwin'):
                    subprocess.call(('open', editPath))
                elif os.name == 'nt':
                    os.startfile(editPath)
                elif os.name == 'posix':
                    subprocess.call(('xdg-open', editPath))
            else:
                pm.displayWarning("Please select one item from the list")
        except Exception:
            pm.displayError("The step can't be find or does't exists")

    @classmethod
    def runStep(self, stepPath, customStepDic):
        try:
            with pm.UndoChunk():
                pm.displayInfo(
                    "EXEC: Executing custom step: %s" % stepPath)
                fileName = os.path.split(stepPath)[1].split(".")[0]
                if os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""):
                    runPath = os.path.join(
                        os.environ.get(
                            MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""), stepPath)
                else:
                    runPath = stepPath
                customStep = imp.load_source(fileName, runPath)
                if hasattr(customStep, "CustomShifterStep"):
                    cs = customStep.CustomShifterStep()
                    cs.run(customStepDic)
                    customStepDic[cs.name] = cs
                    pm.displayInfo(
                        "SUCCEED: Custom Shifter Step Class: %s. "
                        "Succeed!!" % stepPath)
                else:
                    pm.displayInfo(
                        "SUCCEED: Custom Step simple script: %s. "
                        "Succeed!!" % stepPath)

        except Exception as ex:
            template = "An exception of type {0} occured. "
            "Arguments:\n{1!r}"
            message = template.format(type(ex).__name__, ex.args)
            pm.displayError(message)
            pm.displayError(traceback.format_exc())
            cont = pm.confirmBox(
                "FAIL: Custom Step Fail",
                "The step:%s has failed. Continue with next step?" %
                stepPath + "\n\n" + message + "\n\n" +
                traceback.format_exc(),
                "Continue", "Stop Build", "Try Again!")
            if cont == "Stop Build":
                # stop Build
                return True
            elif cont == "Try Again!":
                try:  # just in case there is nothing to undo
                    pm.undo()
                except Exception:
                    pass
                pm.displayInfo("Trying again! : {}".format(stepPath))
                inception = self.runStep(stepPath, customStepDic)
                if inception:  # stops build from the recursion loop.
                    return True
            else:
                return False

    def runManualStep(self, widgetList):
        selItems = widgetList.selectedItems()
        for item in selItems:
            self.runStep(item.text().split("|")[-1][1:], customStepDic={})


class GuideSettingsTab(QtWidgets.QDialog, guui.Ui_Form):

    def __init__(self, parent=None):
        super(guideSettingsTab, self).__init__(parent)
        self.setupUi(self)


class CustomStepTab(QtWidgets.QDialog, csui.Ui_Form):

    def __init__(self, parent=None):
        super(customStepTab, self).__init__(parent)
        self.setupUi(self)


class GuideSettings(MayaQWidgetDockableMixin, QtWidgets.QDialog, HelperSlots):
    # valueChanged = QtCore.Signal(int)
    greenBrush = QtGui.QBrush()
    greenBrush.setColor('#179e83')
    redBrush = QtGui.QBrush()
    redBrush.setColor('#9b2d22')
    whiteBrush = QtGui.QBrush()
    whiteBrush.setColor('#ffffff')
    whiteDownBrush = QtGui.QBrush()
    whiteDownBrush.setColor('#E2E2E2')
    orangeBrush = QtGui.QBrush()
    orangeBrush.setColor('#e67e22')

    def __init__(self, parent=None):
        self.toolName = TYPE
        # Delete old instances of the componet settings window.
        pyqt.deleteInstances(self, MayaQDockWidget)
        # super(self.__class__, self).__init__(parent=parent)
        super(guideSettings, self).__init__()
        # the inspectSettings function set the current selection to the
        # component root before open the settings dialog
        self.root = pm.selected()[0]

        self.guideSettingsTab = guideSettingsTab()
        self.customStepTab = customStepTab()

        self.setup_SettingWindow()
        self.create_controls()
        self.populate_controls()
        self.create_layout()
        self.create_connections()

        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

    def setup_SettingWindow(self):
        self.mayaMainWindow = pyqt.maya_main_window()

        self.setObjectName(self.toolName)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setWindowTitle(TYPE)
        self.resize(500, 615)

    def create_controls(self):
        """Create the controls for the component base"""
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setObjectName("settings_tab")

        # Close Button
        self.close_button = QtWidgets.QPushButton("Close")

    def populate_controls(self):
        """Populate the controls values
            from the custom attributes of the component.

        """
        # populate tab
        self.tabs.insertTab(0, self.guideSettingsTab, "Guide Settings")
        self.tabs.insertTab(1, self.customStepTab, "Custom Steps")

        # populate main settings
        self.guideSettingsTab.rigName_lineEdit.setText(
            self.root.attr("rig_name").get())
        self.guideSettingsTab.mode_comboBox.setCurrentIndex(
            self.root.attr("mode").get())
        self.guideSettingsTab.step_comboBox.setCurrentIndex(
            self.root.attr("step").get())
        self.populateCheck(
            self.guideSettingsTab.proxyChannels_checkBox, "proxyChannels")

        self.populateCheck(self.guideSettingsTab.worldCtl_checkBox, "worldCtl")

        self.populateCheck(
            self.guideSettingsTab.classicChannelNames_checkBox,
            "classicChannelNames")
        self.populateCheck(
            self.guideSettingsTab.importSkin_checkBox, "importSkin")
        self.guideSettingsTab.skin_lineEdit.setText(
            self.root.attr("skin").get())
        self.populateCheck(
            self.guideSettingsTab.jointRig_checkBox, "joint_rig")
        self.populateCheck(
            self.guideSettingsTab.force_uniScale_checkBox, "force_uniScale")
        self.populateAvailableSynopticTabs()

        for item in self.root.attr("synoptic").get().split(","):
            self.guideSettingsTab.rigTabs_listWidget.addItem(item)

        self.guideSettingsTab.L_color_fk_spinBox.setValue(
            self.root.attr("L_color_fk").get())
        self.guideSettingsTab.L_color_ik_spinBox.setValue(
            self.root.attr("L_color_ik").get())
        self.guideSettingsTab.C_color_fk_spinBox.setValue(
            self.root.attr("C_color_fk").get())
        self.guideSettingsTab.C_color_ik_spinBox.setValue(
            self.root.attr("C_color_ik").get())
        self.guideSettingsTab.R_color_fk_spinBox.setValue(
            self.root.attr("R_color_fk").get())
        self.guideSettingsTab.R_color_ik_spinBox.setValue(
            self.root.attr("R_color_ik").get())

        # pupulate custom steps sttings
        self.populateCheck(
            self.customStepTab.preCustomStep_checkBox, "doPreCustomStep")
        for item in self.root.attr("preCustomStep").get().split(","):
            self.customStepTab.preCustomStep_listWidget.addItem(item)
        self.refreshStatusColor(self.customStepTab.preCustomStep_listWidget)

        self.populateCheck(
            self.customStepTab.postCustomStep_checkBox, "doPostCustomStep")
        for item in self.root.attr("postCustomStep").get().split(","):
            self.customStepTab.postCustomStep_listWidget.addItem(item)
        self.refreshStatusColor(self.customStepTab.postCustomStep_listWidget)

    def create_layout(self):
        """
        Create the layout for the component base settings

        """
        self.settings_layout = QtWidgets.QVBoxLayout()
        self.settings_layout.addWidget(self.tabs)
        self.settings_layout.addWidget(self.close_button)

        self.setLayout(self.settings_layout)

    def create_connections(self):
        """Create the slots connections to the controls functions"""
        self.close_button.clicked.connect(self.close_settings)

        # Setting Tab
        tap = self.guideSettingsTab
        tap.rigName_lineEdit.editingFinished.connect(
            partial(self.updateLineEdit,
                    tap.rigName_lineEdit,
                    "rig_name"))
        tap.mode_comboBox.currentIndexChanged.connect(
            partial(self.updateComboBox,
                    tap.mode_comboBox,
                    "mode"))
        tap.step_comboBox.currentIndexChanged.connect(
            partial(self.updateComboBox,
                    tap.step_comboBox,
                    "step"))
        tap.proxyChannels_checkBox.stateChanged.connect(
            partial(self.updateCheck,
                    tap.proxyChannels_checkBox,
                    "proxyChannels"))
        tap.worldCtl_checkBox.stateChanged.connect(
            partial(self.updateCheck,
                    tap.worldCtl_checkBox,
                    "worldCtl"))
        tap.classicChannelNames_checkBox.stateChanged.connect(
            partial(self.updateCheck,
                    tap.classicChannelNames_checkBox,
                    "classicChannelNames"))
        tap.importSkin_checkBox.stateChanged.connect(
            partial(self.updateCheck,
                    tap.importSkin_checkBox,
                    "importSkin"))
        tap.jointRig_checkBox.stateChanged.connect(
            partial(self.updateCheck,
                    tap.jointRig_checkBox,
                    "joint_rig"))
        tap.force_uniScale_checkBox.stateChanged.connect(
            partial(self.updateCheck,
                    tap.force_uniScale_checkBox,
                    "force_uniScale"))
        tap.addTab_pushButton.clicked.connect(
            partial(self.moveFromListWidget2ListWidget,
                    tap.available_listWidget,
                    tap.rigTabs_listWidget,
                    tap.rigTabs_listWidget,
                    "synoptic"))
        tap.removeTab_pushButton.clicked.connect(
            partial(self.moveFromListWidget2ListWidget,
                    tap.rigTabs_listWidget,
                    tap.available_listWidget,
                    tap.rigTabs_listWidget,
                    "synoptic"))
        tap.loadSkinPath_pushButton.clicked.connect(
            self.skinLoad)
        tap.rigTabs_listWidget.installEventFilter(self)

        tap.L_color_fk_spinBox.valueChanged.connect(
            partial(self.updateSpinBox,
                    tap.L_color_fk_spinBox,
                    "L_color_fk"))
        tap.L_color_ik_spinBox.valueChanged.connect(
            partial(self.updateSpinBox,
                    tap.L_color_ik_spinBox,
                    "L_color_ik"))
        tap.C_color_fk_spinBox.valueChanged.connect(
            partial(self.updateSpinBox,
                    tap.C_color_fk_spinBox,
                    "C_color_fk"))
        tap.C_color_ik_spinBox.valueChanged.connect(
            partial(self.updateSpinBox,
                    tap.C_color_ik_spinBox,
                    "C_color_ik"))
        tap.R_color_fk_spinBox.valueChanged.connect(
            partial(self.updateSpinBox,
                    tap.R_color_fk_spinBox,
                    "R_color_fk"))
        tap.R_color_ik_spinBox.valueChanged.connect(
            partial(self.updateSpinBox,
                    tap.R_color_ik_spinBox,
                    "R_color_ik"))

        # custom Step Tab
        csTap = self.customStepTab
        csTap.preCustomStep_checkBox.stateChanged.connect(
            partial(self.updateCheck,
                    csTap.preCustomStep_checkBox,
                    "doPreCustomStep"))
        csTap.preCustomStepAdd_pushButton.clicked.connect(
            self.addCustomStep)
        csTap.preCustomStepNew_pushButton.clicked.connect(
            self.newCustomStep)
        csTap.preCustomStepDuplicate_pushButton.clicked.connect(
            self.duplicateCustomStep)
        csTap.preCustomStepExport_pushButton.clicked.connect(
            self.exportCustomStep)
        csTap.preCustomStepImport_pushButton.clicked.connect(
            self.importCustomStep)
        csTap.preCustomStepRemove_pushButton.clicked.connect(
            partial(self.removeSelectedFromListWidget,
                    csTap.preCustomStep_listWidget,
                    "preCustomStep"))
        csTap.preCustomStep_listWidget.installEventFilter(self)
        csTap.preCustomStepRun_pushButton.clicked.connect(
            partial(self.runManualStep,
                    csTap.preCustomStep_listWidget))
        csTap.preCustomStepEdit_pushButton.clicked.connect(
            partial(self.editFile,
                    csTap.preCustomStep_listWidget))

        csTap.postCustomStep_checkBox.stateChanged.connect(
            partial(self.updateCheck,
                    csTap.postCustomStep_checkBox,
                    "doPostCustomStep"))
        csTap.postCustomStepAdd_pushButton.clicked.connect(
            partial(self.addCustomStep, False))
        csTap.postCustomStepNew_pushButton.clicked.connect(
            partial(self.newCustomStep, False))
        csTap.postCustomStepDuplicate_pushButton.clicked.connect(
            partial(self.duplicateCustomStep, False))
        csTap.postCustomStepExport_pushButton.clicked.connect(
            partial(self.exportCustomStep, False))
        csTap.postCustomStepImport_pushButton.clicked.connect(
            partial(self.importCustomStep, False))
        csTap.postCustomStepRemove_pushButton.clicked.connect(
            partial(self.removeSelectedFromListWidget,
                    csTap.postCustomStep_listWidget,
                    "postCustomStep"))
        csTap.postCustomStep_listWidget.installEventFilter(self)
        csTap.postCustomStepRun_pushButton.clicked.connect(
            partial(self.runManualStep,
                    csTap.postCustomStep_listWidget))
        csTap.postCustomStepEdit_pushButton.clicked.connect(
            partial(self.editFile,
                    csTap.postCustomStep_listWidget))

        # right click menus
        csTap.preCustomStep_listWidget.setContextMenuPolicy(
            QtCore.Qt.CustomContextMenu)
        csTap.preCustomStep_listWidget.customContextMenuRequested.connect(
            self.preCustomStepMenu)
        csTap.postCustomStep_listWidget.setContextMenuPolicy(
            QtCore.Qt.CustomContextMenu)
        csTap.postCustomStep_listWidget.customContextMenuRequested.connect(
            self.postCustomStepMenu)

        # search hightlight
        csTap.preSearch_lineEdit.textChanged.connect(
            self.preHighlightSearch)
        csTap.postSearch_lineEdit.textChanged.connect(
            self.postHighlightSearch)

    def eventFilter(self, sender, event):
        if event.type() == QtCore.QEvent.ChildRemoved:
            if sender == self.guideSettingsTab.rigTabs_listWidget:
                self.updateListAttr(sender, "synoptic")
            elif sender == self.customStepTab.preCustomStep_listWidget:
                self.updateListAttr(sender, "preCustomStep")
            elif sender == self.customStepTab.postCustomStep_listWidget:
                self.updateListAttr(sender, "postCustomStep")
            return True
        else:
            return QtWidgets.QDialog.eventFilter(self, sender, event)

    # Slots ########################################################

    def populateAvailableSynopticTabs(self):

        import mgear.shifter as shifter
        defPath = os.environ.get("MGEAR_SYNOPTIC_PATH", None)
        if not defPath or not os.path.isdir(defPath):
            defPath = shifter.SYNOPTIC_PATH

        tabsDirectories = [name for name in os.listdir(defPath) if
                           os.path.isdir(os.path.join(defPath, name))]
        # Quick clean the first empty item
        if tabsDirectories and not tabsDirectories[0]:
            self.guideSettingsTab.available_listWidget.takeItem(0)

        itemsList = self.root.attr("synoptic").get().split(",")
        for tab in sorted(tabsDirectories):
            if tab not in itemsList:
                self.guideSettingsTab.available_listWidget.addItem(tab)

    def skinLoad(self, *args):
        startDir = self.root.attr("skin").get()
        filePath = pm.fileDialog2(
            dialogStyle=2,
            fileMode=1,
            startingDirectory=startDir,
            okc="Apply",
            fileFilter='mGear skin (*%s)' % skin.FILE_EXT)
        if not filePath:
            return
        if not isinstance(filePath, basestring):
            filePath = filePath[0]

        self.root.attr("skin").set(filePath)
        self.guideSettingsTab.skin_lineEdit.setText(filePath)

    def addCustomStep(self, pre=True, *args):
        """Add a new custom step

        Arguments:
            pre (bool, optional): If true adds the steps to the pre step list
            *args: Maya's Dummy

        Returns:
            None: None
        """

        if pre:
            stepAttr = "preCustomStep"
            stepWidget = self.customStepTab.preCustomStep_listWidget
        else:
            stepAttr = "postCustomStep"
            stepWidget = self.customStepTab.postCustomStep_listWidget

        # Check if we have a custom env for the custom steps initial folder
        if os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""):
            startDir = os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, "")
        else:
            startDir = self.root.attr(stepAttr).get()

        filePath = pm.fileDialog2(
            dialogStyle=2,
            fileMode=1,
            startingDirectory=startDir,
            okc="Add",
            fileFilter='Custom Step .py (*.py)')
        if not filePath:
            return
        if not isinstance(filePath, basestring):
            filePath = filePath[0]

        # Quick clean the first empty item
        itemsList = [i.text() for i in stepWidget.findItems(
            "", QtCore.Qt.MatchContains)]
        if itemsList and not itemsList[0]:
            stepWidget.takeItem(0)

        if os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""):
            filePath = os.path.abspath(filePath)
            baseReplace = os.path.abspath(os.environ.get(
                MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""))
            filePath = filePath.replace(baseReplace, "")[1:]

        fileName = os.path.split(filePath)[1].split(".")[0]
        stepWidget.addItem(fileName + " | " + filePath)
        self.updateListAttr(stepWidget, stepAttr)

    def newCustomStep(self, pre=True, *args):
        """Creates a new custom step

        Arguments:
            pre (bool, optional): If true adds the steps to the pre step list
            *args: Maya's Dummy

        Returns:
            None: None
        """

        if pre:
            stepAttr = "preCustomStep"
            stepWidget = self.customStepTab.preCustomStep_listWidget
        else:
            stepAttr = "postCustomStep"
            stepWidget = self.customStepTab.postCustomStep_listWidget

        # Check if we have a custom env for the custom steps initial folder
        if os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""):
            startDir = os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, "")
        else:
            startDir = self.root.attr(stepAttr).get()

        filePath = pm.fileDialog2(
            dialogStyle=2,
            fileMode=0,
            startingDirectory=startDir,
            okc="New",
            fileFilter='Custom Step .py (*.py)')
        if not filePath:
            return
        if not isinstance(filePath, basestring):
            filePath = filePath[0]

        n, e = os.path.splitext(filePath)
        stepName = os.path.split(n)[-1]
        # raw custome step string
        rawString = r'''
import mgear.shifter.customStep as cstp


class CustomShifterStep(cstp.customShifterMainStep):
    def __init__(self):
        self.name = "%s"


    def run(self, stepDict):
        """Run method.

            i.e:  stepDict["mgearRun"].global_ctl  gets the global_ctl from
                    shifter rig on post step
            i.e:  stepDict["otherCustomStepName"].ctlMesh  gets the ctlMesh
                    from a previous custom step called "otherCustomStepName"
        Arguments:
            stepDict (dict): Dictionary containing the objects from
                the previous steps

        Returns:
            None: None
        """
        return''' % stepName
        f = open(filePath, 'w')
        f.write(rawString + "\n")
        f.close()

        # Quick clean the first empty item
        itemsList = [i.text() for i in stepWidget.findItems(
            "", QtCore.Qt.MatchContains)]
        if itemsList and not itemsList[0]:
            stepWidget.takeItem(0)

        if os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""):
            filePath = os.path.abspath(filePath)
            baseReplace = os.path.abspath(os.environ.get(
                MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""))
            filePath = filePath.replace(baseReplace, "")[1:]

        fileName = os.path.split(filePath)[1].split(".")[0]
        stepWidget.addItem(fileName + " | " + filePath)
        self.updateListAttr(stepWidget, stepAttr)

    def duplicateCustomStep(self, pre=True, *args):
        """Duplicate the selected step

        Arguments:
            pre (bool, optional): If true adds the steps to the pre step list
            *args: Maya's Dummy

        Returns:
            None: None
        """

        if pre:
            stepAttr = "preCustomStep"
            stepWidget = self.customStepTab.preCustomStep_listWidget
        else:
            stepAttr = "postCustomStep"
            stepWidget = self.customStepTab.postCustomStep_listWidget

        # Check if we have a custom env for the custom steps initial folder
        if os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""):
            startDir = os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, "")
        else:
            startDir = self.root.attr(stepAttr).get()

        if stepWidget.selectedItems():
            sourcePath = stepWidget.selectedItems()[0].text().split(
                "|")[-1][1:]

        filePath = pm.fileDialog2(
            dialogStyle=2,
            fileMode=0,
            startingDirectory=startDir,
            okc="New",
            fileFilter='Custom Step .py (*.py)')
        if not filePath:
            return
        if not isinstance(filePath, basestring):
            filePath = filePath[0]

        if os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""):
            sourcePath = os.path.join(startDir, sourcePath)
        shutil.copy(sourcePath, filePath)

        # Quick clean the first empty item
        itemsList = [i.text() for i in stepWidget.findItems(
            "", QtCore.Qt.MatchContains)]
        if itemsList and not itemsList[0]:
            stepWidget.takeItem(0)

        if os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""):
            filePath = os.path.abspath(filePath)
            baseReplace = os.path.abspath(os.environ.get(
                MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""))
            filePath = filePath.replace(baseReplace, "")[1:]

        fileName = os.path.split(filePath)[1].split(".")[0]
        stepWidget.addItem(fileName + " | " + filePath)
        self.updateListAttr(stepWidget, stepAttr)

    def exportCustomStep(self, pre=True, *args):
        """Export custom steps to a json file

        Arguments:
            pre (bool, optional): If true takes the steps from the
                pre step list
            *args: Maya's Dummy

        Returns:
            None: None

        """

        if pre:
            stepWidget = self.customStepTab.preCustomStep_listWidget
        else:
            stepWidget = self.customStepTab.postCustomStep_listWidget

        # Quick clean the first empty item
        itemsList = [i.text() for i in stepWidget.findItems(
            "", QtCore.Qt.MatchContains)]
        if itemsList and not itemsList[0]:
            stepWidget.takeItem(0)

        # Check if we have a custom env for the custom steps initial folder
        if os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""):
            startDir = os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, "")
            itemsList = [os.path.join(startDir, i.text().split("|")[-1][1:])
                         for i in stepWidget.findItems(
                         "", QtCore.Qt.MatchContains)]
        else:
            itemsList = [i.text().split("|")[-1][1:]
                         for i in stepWidget.findItems(
                         "", QtCore.Qt.MatchContains)]
            if itemsList:
                startDir = os.path.split(itemsList[-1])[0]
            else:
                pm.displayWarning("No custom steps to export.")
                return

        stepsDict = {}
        stepsDict["itemsList"] = itemsList
        for item in itemsList:
            step = open(item, "r")
            data = step.read()
            stepsDict[item] = data
            step.close()

        data_string = json.dumps(stepsDict, indent=4, sort_keys=True)
        filePath = pm.fileDialog2(
            dialogStyle=2,
            fileMode=0,
            startingDirectory=startDir,
            fileFilter='Shifter Custom Steps .scs (*%s)' % ".scs")
        if not filePath:
            return
        if not isinstance(filePath, basestring):
            filePath = filePath[0]
        f = open(filePath, 'w')
        f.write(data_string)
        f.close()

    def importCustomStep(self, pre=True, *args):
        """Import custom steps from a json file

        Arguments:
            pre (bool, optional): If true import to pre steps list
            *args: Maya's Dummy

        Returns:
            None: None

        """

        if pre:
            stepAttr = "preCustomStep"
            stepWidget = self.customStepTab.preCustomStep_listWidget
        else:
            stepAttr = "postCustomStep"
            stepWidget = self.customStepTab.postCustomStep_listWidget

        # option import only paths or unpack steps
        option = pm.confirmDialog(
            title='Shifter Custom Step Import Style',
            message='Do you want to import only the path or'
                    ' unpack and import?',
            button=['Only Path', 'Unpack', 'Cancel'],
            defaultButton='Only Path',
            cancelButton='Cancel',
            dismissString='Cancel')

        if option in ['Only Path', 'Unpack']:
            if os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""):
                startDir = os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, "")
            else:
                startDir = pm.workspace(q=True, rootDirectory=True)

            filePath = pm.fileDialog2(
                dialogStyle=2,
                fileMode=1,
                startingDirectory=startDir,
                fileFilter='Shifter Custom Steps .scs (*%s)' % ".scs")
            if not filePath:
                return
            if not isinstance(filePath, basestring):
                filePath = filePath[0]
            stepDict = json.load(open(filePath))
            stepsList = []

        if option == 'Only Path':
            for item in stepDict["itemsList"]:
                stepsList.append(item)

        elif option == 'Unpack':
            unPackDir = pm.fileDialog2(
                dialogStyle=2,
                fileMode=2,
                startingDirectory=startDir)
            if not filePath:
                return
            if not isinstance(unPackDir, basestring):
                unPackDir = unPackDir[0]

            for item in stepDict["itemsList"]:
                fileName = os.path.split(item)[1]
                fileNewPath = os.path.join(unPackDir, fileName)
                stepsList.append(fileNewPath)
                f = open(fileNewPath, 'w')
                f.write(stepDict[item])
                f.close()

        if option in ['Only Path', 'Unpack']:

            for item in stepsList:
                # Quick clean the first empty item
                itemsList = [i.text() for i in stepWidget.findItems(
                    "", QtCore.Qt.MatchContains)]
                if itemsList and not itemsList[0]:
                    stepWidget.takeItem(0)

                if os.environ.get(MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""):
                    item = os.path.abspath(item)
                    baseReplace = os.path.abspath(os.environ.get(
                        MGEAR_SHIFTER_CUSTOMSTEP_KEY, ""))
                    item = item.replace(baseReplace, "")[1:]

                fileName = os.path.split(item)[1].split(".")[0]
                stepWidget.addItem(fileName + " | " + item)
                self.updateListAttr(stepWidget, stepAttr)

    def _customStepMenu(self, cs_listWidget, stepAttr, QPos):
        "right click context menu for custom step"
        currentSelection = cs_listWidget.currentItem()
        if currentSelection is None:
            return
        self.csMenu = QtWidgets.QMenu()
        parentPosition = cs_listWidget.mapToGlobal(QtCore.QPoint(0, 0))
        menu_item_01 = self.csMenu.addAction("Toggle Custom Step")
        self.csMenu.addSeparator()
        menu_item_02 = self.csMenu.addAction("Turn OFF Selected")
        menu_item_03 = self.csMenu.addAction("Turn ON Selected")
        self.csMenu.addSeparator()
        menu_item_04 = self.csMenu.addAction("Turn OFF All")
        menu_item_05 = self.csMenu.addAction("Turn ON All")

        menu_item_01.triggered.connect(partial(self.toggleStatusCustomStep,
                                               cs_listWidget,
                                               stepAttr))
        menu_item_02.triggered.connect(partial(self.setStatusCustomStep,
                                               cs_listWidget,
                                               stepAttr,
                                               False))
        menu_item_03.triggered.connect(partial(self.setStatusCustomStep,
                                               cs_listWidget,
                                               stepAttr,
                                               True))
        menu_item_04.triggered.connect(partial(self.setStatusCustomStep,
                                               cs_listWidget,
                                               stepAttr,
                                               False,
                                               False))
        menu_item_05.triggered.connect(partial(self.setStatusCustomStep,
                                               cs_listWidget,
                                               stepAttr,
                                               True,
                                               False))

        self.csMenu.move(parentPosition + QPos)
        self.csMenu.show()

    def preCustomStepMenu(self, QPos):
        self._customStepMenu(self.customStepTab.preCustomStep_listWidget,
                             "preCustomStep",
                             QPos)

    def postCustomStepMenu(self, QPos):
        self._customStepMenu(self.customStepTab.postCustomStep_listWidget,
                             "postCustomStep",
                             QPos)

    def toggleStatusCustomStep(self, cs_listWidget, stepAttr):
        items = cs_listWidget.selectedItems()
        for item in items:
            if item.text().startswith("*"):
                item.setText(item.text()[1:])
                item.setForeground(self.whiteDownBrush)
            else:
                item.setText("*" + item.text())
                item.setForeground(self.redBrush)

        self.updateListAttr(cs_listWidget, stepAttr)

    def setStatusCustomStep(
            self, cs_listWidget, stepAttr, status=True, selected=True):
        if selected:
            items = cs_listWidget.selectedItems()
        else:
            items = self.getAllItems(cs_listWidget)
        for item in items:
            off = item.text().startswith("*")
            if status and off:
                item.setText(item.text()[1:])
            elif not status and not off:
                item.setText("*" + item.text())
            self.setStatusColor(item)
        self.updateListAttr(cs_listWidget, stepAttr)

    def getAllItems(self, cs_listWidget):
        return [cs_listWidget.item(i) for i in range(cs_listWidget.count())]

    def setStatusColor(self, item):
        if item.text().startswith("*"):
            item.setForeground(self.redBrush)
        else:
            item.setForeground(self.whiteDownBrush)

    def refreshStatusColor(self, cs_listWidget):
        items = self.getAllItems(cs_listWidget)
        for i in items:
            self.setStatusColor(i)

    # Highligter filter
    def _highlightSearch(self, cs_listWidget, searchText):
        items = self.getAllItems(cs_listWidget)
        for i in items:
            if searchText and searchText.lower() in i.text().lower():
                i.setBackground(QtGui.QColor(128, 128, 128, 255))
            else:
                i.setBackground(QtGui.QColor(255, 255, 255, 0))

    def preHighlightSearch(self):
        searchText = self.customStepTab.preSearch_lineEdit.text()
        self._highlightSearch(self.customStepTab.preCustomStep_listWidget,
                              searchText)

    def postHighlightSearch(self):
        searchText = self.customStepTab.postSearch_lineEdit.text()
        self._highlightSearch(self.customStepTab.postCustomStep_listWidget,
                              searchText)


# Backwards compatibility aliases
MainGuide = Main
RigGuide = Rig
helperSlots = HelperSlots
guideSettingsTab = GuideSettingsTab
customStepTab = CustomStepTab
guideSettings = GuideSettings
